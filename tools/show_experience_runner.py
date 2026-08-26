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
import os
import sys
import time
import traceback
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

SHOW_ROOT = Path(__file__).resolve().parents[1]
if str(SHOW_ROOT) not in sys.path:
    sys.path.insert(0, str(SHOW_ROOT))

from tools import show_control_protocol as protocol


def _control_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--wait-for-show-start", action="store_true")
    parser.add_argument("--show-status-heartbeat-hz", type=float, default=1.0)
    args, remaining = parser.parse_known_args(argv)
    if not 0.1 <= args.show_status_heartbeat_hz <= 10.0:
        parser.error("--show-status-heartbeat-hz must be in [0.1, 10.0]")
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


def _show_sha256(path: Path) -> str:
    return hashlib.sha256(path.resolve().read_bytes()).hexdigest()


def make_state_machine_class(base_module: ModuleType, hakopy: Any):
    class ShowExperienceStateMachine(base_module.AssetShowStateMachine):
        def __init__(self, args: argparse.Namespace) -> None:
            super().__init__(args)
            self.wait_for_show_start = bool(args.wait_for_show_start)
            self.run_id = uuid.uuid4().hex
            self.show_sha256 = _show_sha256(args.show_json)
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

    return ShowExperienceStateMachine


def main(argv: list[str] | None = None) -> int:
    source_argv = list(sys.argv[1:] if argv is None else argv)
    control, drone_argv = _control_args(source_argv)
    drone_root = Path(os.environ.get("HAKO_DRONE_ROOT", os.getcwd())).resolve()
    base_module = _load_drone_runner(drone_root)
    hakopy = base_module.hakopy
    args = _parse_drone_args(base_module, drone_argv)
    args.wait_for_show_start = control.wait_for_show_start
    args.show_status_heartbeat_hz = control.show_status_heartbeat_hz
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
