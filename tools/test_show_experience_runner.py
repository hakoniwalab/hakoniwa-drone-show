from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tools import show_control_protocol as protocol
from tools.show_experience_runner import (
    _control_args,
    collision_evaluation,
    enu_to_drone_ros,
    make_state_machine_class,
    resolve_transition_speed,
    show_ir_schedule,
)


def _state(drone_id: str, position: list[float]) -> dict:
    return {
        "drone_id": drone_id,
        "position_m": position,
        "led": {"rgb": [255, 255, 255], "brightness": 1.0},
    }


class _FakeHakopy:
    def __init__(self) -> None:
        self.now_usec = 0
        self.command: bytes | None = None
        self.status_frames: list[bytes] = []

    def simulation_time(self) -> int:
        return self.now_usec

    def pdu_read(self, robot_name: str, channel_id: int, size: int):
        self.asserted_read = (robot_name, channel_id, size)
        return self.command

    def pdu_write(self, robot_name: str, channel_id: int, data: bytes, size: int):
        self.asserted_write = (robot_name, channel_id, size)
        self.status_frames.append(bytes(data))
        return True


class _FakeAssetShowStateMachine:
    def __init__(self, args: Namespace) -> None:
        self.args = args
        self.delta_time_usec = 20_000
        self.failed = False
        self.done = False
        self.prepared = False
        self.failure_logged = False
        self.execution_wall_t0 = None
        self.base_step_count = 0
        self.summary_written = False

    def on_initialize(self) -> int:
        return 0

    def _prepare_services_if_needed(self) -> None:
        self.prepared = True

    def begin_execution_timing(self) -> None:
        self.execution_wall_t0 = 1.0

    def step_once(self) -> None:
        self.base_step_count += 1

    def _write_summary(self, _status: str, _error: str | None = None) -> None:
        self.summary_written = True


class ShowExperienceRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.show_path = Path(self.temp.name) / "show.json"
        self.show_path.write_text('{"meta":{"name":"test"}}\n', encoding="utf-8")
        self.hakopy = _FakeHakopy()
        module = SimpleNamespace(AssetShowStateMachine=_FakeAssetShowStateMachine)
        runner_type = make_state_machine_class(module, self.hakopy)
        self.runner = runner_type(
            Namespace(
                wait_for_show_start=True,
                show_status_heartbeat_hz=1.0,
                show_json=self.show_path,
            )
        )

    def test_waiting_does_not_enter_the_drone_pro_state_machine(self) -> None:
        self.runner.step_once()
        self.assertTrue(self.runner.prepared)
        self.assertFalse(self.runner.execution_released)
        self.assertEqual(self.runner.base_step_count, 0)
        status = protocol.decode_frame(self.hakopy.status_frames[-1])
        self.assertEqual(status["state"], "waiting")

    def test_only_current_run_start_releases_execution_once(self) -> None:
        stale = protocol.start_command(
            run_id="f" * 32,
            show_sha256=self.runner.show_sha256,
            sequence=1,
        )
        self.hakopy.command = protocol.encode_frame(stale)
        self.runner.step_once()
        self.assertFalse(self.runner.execution_released)

        current = protocol.start_command(
            run_id=self.runner.run_id,
            show_sha256=self.runner.show_sha256,
            sequence=1,
        )
        self.hakopy.command = protocol.encode_frame(current)
        self.runner.step_once()
        self.assertTrue(self.runner.execution_released)
        self.assertEqual(self.runner.base_step_count, 0)
        self.assertEqual(
            protocol.decode_frame(self.hakopy.status_frames[-1])["state"], "running"
        )

        self.runner.step_once()
        self.assertEqual(self.runner.base_step_count, 1)

    def test_show_frame_change_publishes_before_heartbeat(self) -> None:
        self.runner._publish_status("running", force=True)
        published = len(self.hakopy.status_frames)

        self.hakopy.now_usec = 100_000
        self.runner._publish_status("running")
        self.assertEqual(len(self.hakopy.status_frames), published)

        self.runner.show_frame_index = 1
        self.runner._publish_status("running")
        self.assertEqual(len(self.hakopy.status_frames), published + 1)
        status = protocol.decode_frame(self.hakopy.status_frames[-1])
        self.assertEqual(status["show_frame_index"], 1)

        self.runner._publish_status("running")
        self.assertEqual(len(self.hakopy.status_frames), published + 1)

    def test_show_time_uses_hakoniwa_time_after_timeline_start(self) -> None:
        self.hakopy.now_usec = 2_000_000
        self.runner.show_timeline_start_simulation_usec = 1_250_000
        self.runner._publish_status("running", force=True)
        status = protocol.decode_frame(self.hakopy.status_frames[-1])
        self.assertEqual(status["simulation_time_usec"], 2_000_000)
        self.assertEqual(status["show_time_usec"], 750_000)

    def test_collision_evaluation_uses_counter_differences(self) -> None:
        report = collision_evaluation(
            {"Drone-1": 4, "Drone-2": 8, "Drone-3": 2},
            {"Drone-1": 7, "Drone-2": 8, "Drone-3": 1},
            baseline_simulation_time_usec=1_000_000,
            final_simulation_time_usec=20_000_000,
        )
        self.assertEqual(report["total_increment"], 3)
        self.assertEqual(report["affected_drone_count"], 1)
        self.assertEqual(report["max_drone_increment"], 3)
        self.assertEqual(report["reset_detected_drones"], ["Drone-3"])
        self.assertIsNone(report["per_drone"]["Drone-3"]["increment"])
        self.assertFalse(report["complete"])

    def test_show_ir_control_argument_is_not_forwarded_to_drone_pro(self) -> None:
        control, remaining = _control_args(
            ["--show-ir", "show-ir.json", "--show-json", "show.json"]
        )
        self.assertEqual(control.show_ir, Path("show-ir.json"))
        self.assertEqual(control.show_status_heartbeat_hz, 4.0)
        self.assertIsNone(control.collision_evaluation_after_sec)
        self.assertEqual(remaining, ["--show-json", "show.json"])

    def test_collision_evaluation_deadline_is_a_show_control_argument(self) -> None:
        control, remaining = _control_args(
            [
                "--collision-evaluation-after-sec",
                "52",
                "--show-json",
                "show.json",
            ]
        )
        self.assertEqual(control.collision_evaluation_after_sec, 52.0)
        self.assertEqual(remaining, ["--show-json", "show.json"])

    def test_collision_evaluation_is_written_at_configured_show_time(self) -> None:
        self.runner.execution_released = True
        self.runner.prepared = True
        self.runner.collision_evaluation_after_sec = 52.0
        self.runner.show_timeline_start_simulation_usec = 1_000_000
        self.runner.collision_baseline_simulation_time_usec = 1_000_000
        self.runner.args.summary_json = Path(self.temp.name) / "summary.json"
        self.hakopy.now_usec = 52_999_999
        self.runner._capture_collision_final = mock.Mock(return_value=[])
        self.runner._write_summary = mock.Mock()

        self.runner.step_once()
        self.runner._capture_collision_final.assert_not_called()

        self.hakopy.now_usec = 53_000_000
        self.runner.step_once()
        self.runner._capture_collision_final.assert_called_once_with()
        self.runner._write_summary.assert_called_once_with("evaluation_completed")
        self.assertTrue(self.runner.collision_evaluation_written)

    def test_show_ir_schedule_resolves_transition_and_hold_frames(self) -> None:
        show_ir = {
            "timeline": [
                {"time_sec": 0.0, "states": [_state("Drone-1", [0, 0, 0])]},
                {"time_sec": 8.0, "states": [_state("Drone-1", [1, 0, 5])]},
                {"time_sec": 14.0, "states": [_state("Drone-1", [1, 0, 5])]},
                {"time_sec": 22.0, "states": [_state("Drone-1", [2, 0, 5])]},
                {"time_sec": 28.0, "states": [_state("Drone-1", [2, 0, 5])]},
            ]
        }
        initial_hold, motions = show_ir_schedule(show_ir)
        self.assertEqual(initial_hold, 0.0)
        self.assertEqual([motion.duration_sec for motion in motions], [8.0, 8.0])
        self.assertEqual([motion.hold_sec for motion in motions], [6.0, 6.0])
        self.assertEqual(
            [motion.target_frame_index for motion in motions], [1, 3]
        )

    def test_show_ir_enu_is_converted_once_for_drone_goto(self) -> None:
        self.assertEqual(enu_to_drone_ros([12.0, 34.0, 56.0]), (34.0, -12.0, 56.0))

    def test_show_ir_speed_follows_frame_time_unless_explicitly_capped(self) -> None:
        current = (0.0, 0.0, 0.0)
        target = (0.0, 6.0, 8.0)
        self.assertEqual(resolve_transition_speed(current, target, 2.0), 5.0)
        self.assertEqual(
            resolve_transition_speed(
                current, target, 2.0, maximum_speed_m_s=3.0
            ),
            3.0,
        )


if __name__ == "__main__":
    unittest.main()
