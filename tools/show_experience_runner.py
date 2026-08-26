#!/usr/bin/env python3
"""Drone Show runner that waits for a browser START command without blocking time.

The proven Drone PRO ``AssetShowStateMachine`` remains the flight-control
implementation.  This runner subclasses it only to add a PDU-backed start gate
and minimal lifecycle status required by the browser experience.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import sys
import time
import traceback
import uuid
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

SHOW_ROOT = Path(__file__).resolve().parents[1]
if str(SHOW_ROOT) not in sys.path:
    sys.path.insert(0, str(SHOW_ROOT))

from tools import show_control_protocol as protocol
from tools.show_ir import ShowIrValidationError, validate_show_ir


@dataclass(frozen=True)
class ShowIrMotion:
    source_time_sec: float
    target_time_sec: float
    target_frame_index: int
    target_states: tuple[dict[str, Any], ...]
    hold_sec: float

    @property
    def duration_sec(self) -> float:
        return self.target_time_sec - self.source_time_sec


def _control_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--wait-for-show-start", action="store_true")
    parser.add_argument("--show-status-heartbeat-hz", type=float, default=1.0)
    parser.add_argument(
        "--show-ir",
        type=Path,
        help="Execute a resolved Hakoniwa Show IR instead of the legacy show.json",
    )
    parser.add_argument(
        "--show-ir-max-speed-m-s",
        type=float,
        help="Optional safety cap for speeds resolved from Show IR frame times",
    )
    args, remaining = parser.parse_known_args(argv)
    if not 0.1 <= args.show_status_heartbeat_hz <= 10.0:
        parser.error("--show-status-heartbeat-hz must be in [0.1, 10.0]")
    if args.show_ir_max_speed_m_s is not None and args.show_ir_max_speed_m_s <= 0:
        parser.error("--show-ir-max-speed-m-s must be positive")
    return args, remaining


def _load_drone_runner(drone_root: Path) -> ModuleType:
    path = (
        drone_root.resolve()
        / "drone_api"
        / "external_rpc"
        / "apps"
        / "show_asset_runner.py"
    )
    if not path.is_file():
        raise RuntimeError(f"Drone PRO show runner not found: {path}")
    # Executing show_asset_runner.py directly places its apps directory on
    # sys.path. Reproduce that contract when loading it as a module so its
    # sibling show_runner.py remains resolvable without modifying Drone PRO.
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("drone_pro_show_asset_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Drone PRO show runner: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _parse_drone_args(module: ModuleType, argv: list[str]) -> argparse.Namespace:
    original = sys.argv
    try:
        sys.argv = [str(Path(__file__).resolve()), *argv]
        return module.parse_args()
    finally:
        sys.argv = original


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.resolve().read_bytes()).hexdigest()


def _load_show_ir(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.resolve().read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"cannot read Show IR {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"invalid Show IR JSON {path}:{exc.lineno}:{exc.colno}: {exc.msg}"
        ) from exc
    try:
        resolved = validate_show_ir(value)
    except ShowIrValidationError as exc:
        raise RuntimeError(f"invalid Show IR {path}: {exc}") from exc
    if "placement" in resolved:
        raise RuntimeError(
            "Show IR placement is not supported by the local City runtime adapter; "
            "compile positions relative to the configured City World origin"
        )
    return resolved


def _same_positions(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    return all(
        all(
            math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-9)
            for a, b in zip(left_state["position_m"], right_state["position_m"])
        )
        for left_state, right_state in zip(left, right)
    )


def show_ir_schedule(
    show_ir: dict[str, Any],
) -> tuple[float, tuple[ShowIrMotion, ...]]:
    """Resolve Show IR frames into movement segments and endpoint holds."""

    frames = show_ir["timeline"]
    initial_hold_sec = 0.0
    motions: list[ShowIrMotion] = []
    previous = frames[0]
    for frame_index, frame in enumerate(frames[1:], start=1):
        elapsed = float(frame["time_sec"]) - float(previous["time_sec"])
        if _same_positions(previous["states"], frame["states"]):
            if motions:
                last = motions[-1]
                motions[-1] = ShowIrMotion(
                    source_time_sec=last.source_time_sec,
                    target_time_sec=last.target_time_sec,
                    target_frame_index=last.target_frame_index,
                    target_states=last.target_states,
                    hold_sec=last.hold_sec + elapsed,
                )
            else:
                initial_hold_sec += elapsed
        else:
            motions.append(
                ShowIrMotion(
                    source_time_sec=float(previous["time_sec"]),
                    target_time_sec=float(frame["time_sec"]),
                    target_frame_index=frame_index,
                    target_states=tuple(frame["states"]),
                    hold_sec=0.0,
                )
            )
        previous = frame
    return initial_hold_sec, tuple(motions)


def enu_to_drone_ros(position_m: list[float]) -> tuple[float, float, float]:
    """Convert Show IR ENU into the DroneGoTo ROS/NWU request frame."""

    east, north, up = (float(component) for component in position_m)
    return north, -east, up


def resolve_transition_speed(
    current: tuple[float, float, float],
    target: tuple[float, float, float],
    duration_sec: float,
    *,
    maximum_speed_m_s: float | None = None,
) -> float:
    """Resolve constant straight-line speed, optionally applying a safety cap."""

    speed = max(0.01, math.dist(current, target) / duration_sec)
    return min(float(maximum_speed_m_s), speed) if maximum_speed_m_s else speed


def _completed_success_future() -> Future:
    future: Future = Future()
    future.set_result(SimpleNamespace(ok=True, message="already at target"))
    return future


def make_state_machine_class(base_module: ModuleType, hakopy: Any):
    class ShowExperienceStateMachine(base_module.AssetShowStateMachine):
        def __init__(self, args: argparse.Namespace) -> None:
            self.show_ir_path = getattr(args, "show_ir", None)
            self.show_ir: dict[str, Any] | None = None
            self.ir_initial_hold_sec = 0.0
            self.ir_motions: tuple[ShowIrMotion, ...] = ()
            if self.show_ir_path is None:
                super().__init__(args)
            else:
                self.show_ir_path = self.show_ir_path.resolve()
                self.show_ir = _load_show_ir(self.show_ir_path)
                self.ir_initial_hold_sec, self.ir_motions = show_ir_schedule(
                    self.show_ir
                )
                self._initialize_show_ir_runtime(args)
            self.wait_for_show_start = bool(args.wait_for_show_start)
            self.run_id = uuid.uuid4().hex
            runtime_input = self.show_ir_path or args.show_json
            self.show_sha256 = _file_sha256(runtime_input)
            self.start_gate = protocol.StartGate(
                run_id=self.run_id, show_sha256=self.show_sha256
            )
            self.status_sequence = 0
            self.status_state: str | None = None
            self.status_error: str | None = None
            self.last_status_simulation_usec: int | None = None
            self.heartbeat_interval_usec = int(
                1_000_000 / float(args.show_status_heartbeat_hz)
            )
            self.execution_released = not self.wait_for_show_start
            self.show_frame_index = 0 if self.show_ir is not None else None

        def _initialize_show_ir_runtime(self, args: argparse.Namespace) -> None:
            """Initialize Drone PRO execution state without reading legacy show.json."""

            assert self.show_ir is not None
            self.args = args
            self.delta_time_usec = int(args.delta_time_msec) * 1000
            self.meta = {
                "name": self.show_ir.get("title", self.show_ir["show_id"]),
                "show_id": self.show_ir["show_id"],
            }
            self.options = {}
            self.formations = {}
            self.timeline = self.show_ir["timeline"]
            self.drone_names = self._resolve_drones()
            if self.show_ir["drone_ids"] != self.drone_names:
                raise RuntimeError(
                    "Show IR Drone IDs and order must exactly match the runtime fleet"
                )
            airborne_altitudes = [
                float(state["position_m"][2])
                for frame in self.show_ir["timeline"][1:]
                for state in frame["states"]
            ]
            if not airborne_altitudes:
                airborne_altitudes = [
                    float(state["position_m"][2])
                    for state in self.show_ir["timeline"][0]["states"]
                ]
            self.center = [0.0, 0.0, 0.0]
            self.scale = 1.0
            self.base_alt = min(airborne_altitudes)
            self.z_offset_m = float(args.z_offset_m)
            if not math.isclose(self.z_offset_m, 0.0):
                raise RuntimeError(
                    "--z-offset-m cannot be applied to already resolved Show IR"
                )
            self.takeoff_alt = (
                float(args.takeoff_alt)
                if args.takeoff_alt is not None
                else max(0.5, self.base_alt)
            )
            self.estimated_positions = None
            self.pending = []
            self.phase_index = 0
            self.hold_remaining_usec = 0
            self.final_settle_remaining_usec = 0
            self.done = False
            self.failed = False
            self.failure_logged = False
            self.prepared = False
            self.prepare_attempts = 0
            self.fleet = None
            self.total_t0 = time.perf_counter()
            self.execution_wall_t0 = None
            self.simulation_start_usec = None
            self.real_time_sync_sleep_count = 0
            self.real_time_sync_sleep_sec = 0.0
            self.prepare_t0 = None
            self.phase_t0 = None
            self.phase_simulation_t0_usec = None
            self.phase_times = {}
            self.phase_simulation_times_sec = {}
            self.summary_written = False
            self.phases = self._build_show_ir_phases()

        def _initial_ir_positions(self) -> dict[str, tuple[float, float, float]]:
            assert self.show_ir is not None
            positions = {
                state["drone_id"]: enu_to_drone_ros(state["position_m"])
                for state in self.show_ir["timeline"][0]["states"]
            }
            # DroneTakeOff preserves horizontal position and resolves vertical
            # position from --takeoff-alt.
            return {
                drone_id: (position[0], position[1], float(self.takeoff_alt))
                for drone_id, position in positions.items()
            }

        def _build_show_ir_phases(self) -> list[Any]:
            phases = [
                base_module.Phase(
                    name="set_ready",
                    submit=lambda: self.fleet.set_ready_async_all(),
                    on_complete=self._on_simple_complete("set_ready"),
                ),
                base_module.Phase(
                    name="takeoff",
                    submit=lambda: self.fleet.takeoff_async_all(self.takeoff_alt),
                    on_complete=self._on_ir_takeoff_complete,
                ),
            ]
            for index, motion in enumerate(self.ir_motions, start=1):
                phases.append(
                    base_module.Phase(
                        name=f"ir-goto#{index}@{motion.target_time_sec:g}s",
                        submit=self._make_ir_goto_submit(motion),
                        on_complete=self._make_ir_goto_complete(
                            motion,
                            final_motion=index == len(self.ir_motions),
                        ),
                    )
                )
            if self.args.land:
                phases.append(
                    base_module.Phase(
                        name="land",
                        submit=lambda: self.fleet.land_async_all(),
                        on_complete=self._on_simple_complete("land"),
                    )
                )
            return phases

        def _on_ir_takeoff_complete(self, results: list[Any]) -> None:
            if base_module.any_failed(results):
                raise RuntimeError("takeoff failed")
            self.estimated_positions = self._initial_ir_positions()
            hold_sec = self.ir_initial_hold_sec
            if not self.ir_motions and not self.args.land:
                hold_sec += max(0.0, float(self.args.final_hold_extra_sec))
            self.hold_remaining_usec = int(max(0.0, hold_sec) * 1_000_000)

        def _make_ir_goto_submit(self, motion: ShowIrMotion):
            targets = {
                state["drone_id"]: enu_to_drone_ros(state["position_m"])
                for state in motion.target_states
            }

            def submit() -> list[Any]:
                assert self.estimated_positions is not None
                futures: list[Any] = []
                required_speeds: list[float] = []
                maximum_speed = getattr(self.args, "show_ir_max_speed_m_s", None)
                for drone_id in self.drone_names:
                    current = self.estimated_positions[drone_id]
                    target = targets[drone_id]
                    distance = math.dist(current, target)
                    if distance <= 1e-9:
                        futures.append(_completed_success_future())
                        continue
                    required_speed = distance / motion.duration_sec
                    required_speeds.append(required_speed)
                    speed = resolve_transition_speed(
                        current,
                        target,
                        motion.duration_sec,
                        maximum_speed_m_s=maximum_speed,
                    )
                    futures.append(
                        self.fleet.clients[drone_id].goto_async(
                            target[0],
                            target[1],
                            target[2],
                            yaw_deg=0.0,
                            speed_m_s=speed,
                            tolerance_m=self.args.tolerance,
                            timeout_sec=max(
                                self.args.timeout_sec, motion.duration_sec + 10.0
                            ),
                        )
                    )
                if (
                    maximum_speed is not None
                    and required_speeds
                    and max(required_speeds) > float(maximum_speed)
                ):
                    print(
                        "WARN: Show IR transition exceeds configured max speed; "
                        f"target_time_sec={motion.target_time_sec:g} "
                        f"required_max_m_s={max(required_speeds):.3f} "
                        f"configured_max_m_s={float(maximum_speed):.3f}"
                    )
                self._current_assignments = targets
                return futures

            return submit

        def _make_ir_goto_complete(
            self, motion: ShowIrMotion, *, final_motion: bool
        ):
            def complete(results: list[Any]) -> None:
                if base_module.any_failed(results):
                    raise RuntimeError(
                        f"Show IR goto failed at {motion.target_time_sec:g} sec"
                    )
                self.estimated_positions = dict(self._current_assignments)
                self.show_frame_index = motion.target_frame_index
                hold_sec = motion.hold_sec
                if final_motion and not self.args.land:
                    hold_sec += max(0.0, float(self.args.final_hold_extra_sec))
                self.hold_remaining_usec = int(max(0.0, hold_sec) * 1_000_000)

            return complete

        def _simulation_time(self) -> int:
            return max(0, int(hakopy.simulation_time()))

        def _publish_status(
            self,
            state: str,
            *,
            error: str | None = None,
            force: bool = False,
        ) -> None:
            now = self._simulation_time()
            heartbeat_due = (
                self.last_status_simulation_usec is None
                or now - self.last_status_simulation_usec >= self.heartbeat_interval_usec
            )
            changed = state != self.status_state or error != self.status_error
            if not force and not changed and not heartbeat_due:
                return
            self.status_sequence += 1
            message = protocol.show_status(
                state=state,
                run_id=self.run_id,
                show_sha256=self.show_sha256,
                sequence=self.status_sequence,
                simulation_time_usec=now,
                show_frame_index=self.show_frame_index,
                error=error,
            )
            # hakopy's native binding requires a mutable bytearray even though
            # the protocol frame itself is immutable at the application level.
            frame = bytearray(protocol.encode_frame(message))
            if not hakopy.pdu_write(
                protocol.ROBOT_NAME,
                protocol.STATUS_CHANNEL_ID,
                frame,
                len(frame),
            ):
                raise RuntimeError("failed to write Drone Show status PDU")
            self.status_state = state
            self.status_error = error
            self.last_status_simulation_usec = now

        def _read_command(self) -> dict[str, Any] | None:
            raw = hakopy.pdu_read(
                protocol.ROBOT_NAME,
                protocol.COMMAND_CHANNEL_ID,
                protocol.FRAME_SIZE,
            )
            if raw is None:
                return None
            try:
                return protocol.decode_frame(raw)
            except protocol.ProtocolError as exc:
                # A partially written or unrelated command never stops the
                # simulation clock. Keep waiting and surface one concise log.
                print(f"WARN: ignored invalid Drone Show command PDU: {exc}")
                return None

        def on_initialize(self) -> int:
            result = super().on_initialize()
            if self.show_ir is not None and not self.failed:
                print(
                    "INFO: show_ir_runtime "
                    f"path={self.show_ir_path} "
                    f"frames={len(self.show_ir['timeline'])} "
                    f"motions={len(self.ir_motions)}"
                )
            if self.failed:
                self._publish_status(
                    "failed", error="show runner initialization failed", force=True
                )
            else:
                self._publish_status("initializing", force=True)
            return result

        def step_once(self) -> None:
            if self.failed:
                self._publish_status(
                    "failed", error="show runner failed", force=True
                )
                return
            if self.done:
                self._publish_status("completed")
                return
            if not self.execution_released:
                if not self.prepared:
                    self._prepare_services_if_needed()
                if self.prepared:
                    self._publish_status("waiting")
                    if self.start_gate.accept(self._read_command()):
                        self.execution_released = True
                        self.begin_execution_timing()
                        self._publish_status("running", force=True)
                        print(
                            "INFO: drone_show_start_accepted "
                            f"run_id={self.run_id} show_sha256={self.show_sha256}"
                        )
                else:
                    self._publish_status("initializing")
                return
            if self.execution_wall_t0 is None:
                self.begin_execution_timing()
            super().step_once()
            if self.failed:
                self._publish_status("failed", error="show runner failed", force=True)
            elif self.done:
                self._publish_status("completed", force=True)
            else:
                self._publish_status("running")

        def _write_summary(self, status: str, error: str | None = None) -> None:
            was_written = self.summary_written
            super()._write_summary(status, error)
            if (
                self.show_ir_path is None
                or was_written
                or not self.summary_written
                or getattr(self.args, "summary_json", None) is None
            ):
                return
            path = self.args.summary_json.resolve()
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload.pop("show_json", None)
            payload["runtime_input"] = {
                "type": "show_ir",
                "path": str(self.show_ir_path),
                "sha256": self.show_sha256,
            }
            path.write_text(
                json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
                encoding="utf-8",
            )

    return ShowExperienceStateMachine


def main(argv: list[str] | None = None) -> int:
    source_argv = list(sys.argv[1:] if argv is None else argv)
    control, drone_argv = _control_args(source_argv)
    drone_root = Path(os.environ.get("HAKO_DRONE_ROOT", os.getcwd())).resolve()
    base_module = _load_drone_runner(drone_root)
    hakopy = base_module.hakopy
    if control.show_ir is not None and "--show-json" not in drone_argv:
        # Drone PRO's unchanged parser still declares --show-json as required.
        # In IR mode it is not read; use the IR path only to satisfy that
        # compatibility parser contract.
        drone_argv.extend(["--show-json", str(control.show_ir)])
    args = _parse_drone_args(base_module, drone_argv)
    args.wait_for_show_start = control.wait_for_show_start
    args.show_status_heartbeat_hz = control.show_status_heartbeat_hz
    args.show_ir = control.show_ir
    args.show_ir_max_speed_m_s = control.show_ir_max_speed_m_s
    runner_class = make_state_machine_class(base_module, hakopy)
    runner = runner_class(args)

    runtime_service_config_path = base_module.create_runtime_service_config(
        args.service_config_path.resolve()
    )
    if args.pdu_config_path is not None:
        pdu_config_path = args.pdu_config_path.resolve()
    else:
        import json

        runtime_service = json.loads(runtime_service_config_path.read_text())
        runtime_pdu_config_path = runtime_service.get("pdu_config_path")
        if not runtime_pdu_config_path:
            raise SystemExit(
                f"pdu_config_path is missing in runtime service config: {runtime_service_config_path}"
            )
        pdu_config_path = Path(runtime_pdu_config_path).resolve()

    def on_initialize(_context) -> int:
        return runner.on_initialize()

    def on_reset(_context) -> int:
        return 0

    def on_manual_timing_control(_context) -> int:
        try:
            while not runner.done and not runner.failed:
                runner.step_once()
                # This call is unconditional while waiting. Blocking on a
                # browser socket here would stop the entire Hakoniwa clock.
                if not hakopy.usleep(runner.delta_time_usec):
                    runner.failed = True
                    runner._publish_status(
                        "failed", error="hakopy.usleep() failed", force=True
                    )
                    runner._write_summary("failed", "hakopy.usleep() failed")
                    return 0
                if runner.execution_released:
                    runner.synchronize_wall_to_simulation_time()
            if runner.failed:
                runner._publish_status(
                    "failed", error="show runner failed", force=True
                )
            return 0
        except Exception as exc:
            runner.failed = True
            if not runner.failure_logged:
                runner.failure_logged = True
                print(f"ERROR: Show Experience Runner failed: {exc}")
                traceback.print_exc()
            try:
                runner._publish_status("failed", error=str(exc), force=True)
            except Exception:
                traceback.print_exc()
            runner._write_summary("failed", str(exc))
            return 0

    callbacks = {
        "on_initialize": on_initialize,
        "on_simulation_step": None,
        "on_manual_timing_control": on_manual_timing_control,
        "on_reset": on_reset,
    }
    registered = hakopy.asset_register(
        args.asset_name,
        str(pdu_config_path),
        callbacks,
        runner.delta_time_usec,
        hakopy.HAKO_ASSET_MODEL_CONTROLLER,
    )
    if registered is False:
        print(f"ERROR: hako_asset_register() returns {registered}.")
        return 1
    started = hakopy.start()
    print(f"INFO: hako_asset_start() returns {started}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
