#!/usr/bin/env python3
"""Uniform Global Wind Hakoniwa asset for a Drone Show fleet."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

SHOW_ROOT = Path(__file__).resolve().parents[1]
if str(SHOW_ROOT) not in sys.path:
    sys.path.insert(0, str(SHOW_ROOT))

import hakopy
from hakoniwa_pdu.impl.shm_communication_service import ShmCommunicationService
from hakoniwa_pdu.pdu_manager import PduManager
from hakoniwa_pdu.pdu_msgs.hako_msgs.pdu_conv_Disturbance import (
    py_to_pdu_Disturbance,
)
from hakoniwa_pdu.pdu_msgs.hako_msgs.pdu_pytype_Disturbance import Disturbance
from hakoniwa_pdu_endpoint.c_endpoint import Endpoint, PduResolvedKey

from tools import global_wind_protocol as protocol
from tools import show_control_protocol
from tools.global_wind_fanout import (
    GlobalWindAssetRuntime,
    GlobalWindFanout,
    GlobalWindFanoutError,
)
from tools.wind_scenario import WindScenarioError, WindScenarioPlayer, load_wind_scenario


def resolve_drone_names(pdu_config_path: Path) -> tuple[str, ...]:
    try:
        config = json.loads(pdu_config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GlobalWindFanoutError(f"cannot read PDU config: {exc}") from exc
    names = tuple(
        robot.get("name")
        for robot in config.get("robots", [])
        if isinstance(robot, dict)
        and isinstance(robot.get("name"), str)
        and robot.get("name") != protocol.ROBOT_NAME
    )
    if not names:
        raise GlobalWindFanoutError("PDU config contains no Drone robots")
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint-config", type=Path, required=True)
    parser.add_argument("--pdu-config-path", type=Path, required=True)
    parser.add_argument("--asset-name", default="GlobalWindAsset")
    parser.add_argument("--delta-time-msec", type=int, default=20)
    parser.add_argument(
        "--scenario",
        type=Path,
        help="Replay a validated wind scenario using Show Status show_time_usec",
    )
    args = parser.parse_args(argv)
    if args.delta_time_msec < 1:
        parser.error("--delta-time-msec must be positive")

    pdu_config_path = args.pdu_config_path.resolve()
    scenario_player = None
    if args.scenario is not None:
        try:
            scenario_player = WindScenarioPlayer(load_wind_scenario(args.scenario))
        except WindScenarioError as exc:
            parser.error(str(exc))
    drone_names = resolve_drone_names(pdu_config_path)
    manager = PduManager()
    manager.initialize(
        config_path=str(pdu_config_path), comm_service=ShmCommunicationService()
    )
    if not manager.start_service_nowait():
        print("ERROR: failed to start Global Wind SHM service", file=sys.stderr)
        return 1
    fanout = GlobalWindFanout(
        manager=manager,
        drone_names=drone_names,
        disturbance_factory=Disturbance,
        disturbance_encoder=py_to_pdu_Disturbance,
    )

    endpoint = Endpoint("global_wind_asset", "in")
    key = PduResolvedKey(
        robot=protocol.ROBOT_NAME, channel_id=protocol.COMMAND_CHANNEL_ID
    )

    def log_result(prefix: str, result) -> None:
        print(
            f"[GLOBAL_WIND] {prefix} drones={result.drone_count} "
            f"elapsed_msec={result.elapsed_msec:.3f}",
            flush=True,
        )

    def on_wind(_key, payload: bytes) -> None:
        if scenario_player is not None:
            return
        try:
            message = protocol.decode_frame(payload)
            if message is None:
                return
            result = fanout.accept(message)
            if not result.changed:
                print("[GLOBAL_WIND] unchanged; fan-out skipped", flush=True)
                return
            wind = message["wind"]
            log_result(
                f"changed enabled={str(wind['enabled']).lower()} "
                f"vector_ros_m_s={wind['vector_ros_m_s']} "
                f"speed_stddev_m_s={wind['variation']['speed_stddev_m_s']} "
                f"seed={wind['variation']['seed']}",
                result,
            )
        except (protocol.GlobalWindProtocolError, GlobalWindFanoutError) as exc:
            print(f"[GLOBAL_WIND] rejected: {exc}", flush=True)
        except Exception:
            print("[GLOBAL_WIND] callback failed", file=sys.stderr, flush=True)
            traceback.print_exc()

    endpoint.open(str(args.endpoint_config.resolve()), asset_name=args.asset_name)
    endpoint.subscribe_on_recv_callback(key, on_wind)
    endpoint.start()
    runtime = GlobalWindAssetRuntime(
        manager=manager, fanout=fanout, endpoint=endpoint
    )

    def on_initialize(_context) -> int:
        try:
            log_result("initialized no-wind", runtime.initialize())
            print("[GLOBAL_WIND] SHM callback ready", flush=True)
            return 0
        except GlobalWindFanoutError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    def on_reset(_context) -> int:
        try:
            log_result("reset reapplied", runtime.reset())
            return 0
        except GlobalWindFanoutError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    def on_manual_timing_control(_context) -> int:
        while hakopy.usleep(args.delta_time_msec * 1000):
            if scenario_player is None:
                continue
            raw = hakopy.pdu_read(
                show_control_protocol.ROBOT_NAME,
                show_control_protocol.STATUS_CHANNEL_ID,
                show_control_protocol.FRAME_SIZE,
            )
            if raw is None:
                continue
            try:
                status = show_control_protocol.decode_frame(raw)
                if status is None:
                    continue
                for command in scenario_player.observe_status(status):
                    result = fanout.accept(command)
                    event = command["wind"]
                    log_result(
                        "scenario "
                        f"show_time_usec={status['show_time_usec']} "
                        f"enabled={str(event['enabled']).lower()} "
                        f"vector_ros_m_s={event['vector_ros_m_s']}",
                        result,
                    )
            except (
                show_control_protocol.ProtocolError,
                WindScenarioError,
                protocol.GlobalWindProtocolError,
                GlobalWindFanoutError,
            ) as exc:
                print(f"[GLOBAL_WIND] scenario status rejected: {exc}", flush=True)
        return 0

    callbacks = {
        "on_initialize": on_initialize,
        "on_simulation_step": None,
        "on_manual_timing_control": on_manual_timing_control,
        "on_reset": on_reset,
    }
    try:
        registered = hakopy.asset_register(
            args.asset_name,
            str(pdu_config_path),
            callbacks,
            args.delta_time_msec * 1000,
            hakopy.HAKO_ASSET_MODEL_CONTROLLER,
        )
        if registered is False:
            print(f"ERROR: hakopy.asset_register returned {registered}", file=sys.stderr)
            return 1
        started = hakopy.start()
        print(f"INFO: hako_asset_start() returns {started}", flush=True)
        return 0
    finally:
        manager.stop_service_nowait()
        endpoint.stop()
        endpoint.close()


if __name__ == "__main__":
    raise SystemExit(main())
