from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tools.initial_fleet_state import generate_grid
from tools.show_compiler import ShowCompileError, assign_point_indices, compile_show, transform_position
from tools.show_ir import validate_show_ir


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "examples" / "show-plans" / "three-face-demo.json"


class ShowCompilerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        self.initial = generate_grid(
            drone_count=128,
            prefix="Drone-",
            start=1,
            zero_padding=0,
            spacing_m=1.5,
            altitude_m=0.0,
        )

    def compile(self) -> dict:
        return compile_show(self.plan, self.initial, plan_directory=PLAN_PATH.parent)

    def test_three_face_plan_compiles_to_complete_ir(self) -> None:
        result = self.compile()
        self.assertIs(validate_show_ir(result), result)
        self.assertEqual(len(result["drone_ids"]), 128)
        self.assertEqual(
            [frame["time_sec"] for frame in result["timeline"]],
            [0.0, 8.0, 14.0, 22.0, 28.0, 36.0, 42.0],
        )

    def test_hold_frames_keep_positions_and_led(self) -> None:
        result = self.compile()
        for arrival, hold in ((1, 2), (3, 4), (5, 6)):
            self.assertEqual(result["timeline"][arrival]["states"], result["timeline"][hold]["states"])

    def test_led_role_override_is_resolved_per_drone(self) -> None:
        result = self.compile()
        cat_arrival = result["timeline"][3]["states"]
        colors = {tuple(state["led"]["rgb"]) for state in cat_arrival}
        self.assertEqual(colors, {(255, 255, 255), (80, 160, 255)})
        self.assertEqual(sum(state["led"]["rgb"] == [80, 160, 255] for state in cat_arrival), 19)

    def test_compilation_is_deterministic(self) -> None:
        self.assertEqual(self.compile(), self.compile())

    def test_initial_ids_must_match_plan(self) -> None:
        initial = copy.deepcopy(self.initial)
        initial["states"].reverse()
        with self.assertRaisesRegex(ShowCompileError, "IDs and order"):
            compile_show(self.plan, initial, plan_directory=PLAN_PATH.parent)

    def test_nearest_greedy_assignment(self) -> None:
        assignments = assign_point_indices(
            [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]],
            [[9.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            "nearest-greedy",
        )
        self.assertEqual(assignments, [1, 0])

    def test_transform_maps_right_up_depth_to_enu(self) -> None:
        transform = {
            "scale_m": 2.0,
            "translation_m": [10.0, 20.0, 30.0],
            "yaw_deg": 0.0,
            "tilt_deg": 0.0,
        }
        self.assertEqual(transform_position([1.0, 2.0, 3.0], transform), [12.0, 26.0, 34.0])


if __name__ == "__main__":
    unittest.main()
