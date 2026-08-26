from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tools.show_plan import ShowPlanValidationError, validate_show_plan


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "examples" / "show-plans" / "three-face-demo.json"


class ShowPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.value = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    def test_example_and_formation_references_are_valid(self) -> None:
        self.assertIs(
            validate_show_plan(self.value, base_directory=PLAN_PATH.parent),
            self.value,
        )

    def test_formation_ids_are_unique(self) -> None:
        self.value["formations"][1]["formation_id"] = self.value["formations"][0]["formation_id"]
        with self.assertRaisesRegex(ShowPlanValidationError, "formation_id values must be unique"):
            validate_show_plan(self.value)

    def test_timeline_references_known_formation(self) -> None:
        self.value["timeline"][0]["formation_id"] = "missing"
        with self.assertRaisesRegex(ShowPlanValidationError, "must reference an entry"):
            validate_show_plan(self.value)

    def test_step_ids_are_unique(self) -> None:
        self.value["timeline"][1]["step_id"] = self.value["timeline"][0]["step_id"]
        with self.assertRaisesRegex(ShowPlanValidationError, "step_id values must be unique"):
            validate_show_plan(self.value)

    def test_transition_duration_must_be_positive(self) -> None:
        self.value["defaults"]["transition_sec"] = 0
        with self.assertRaisesRegex(ShowPlanValidationError, "must be positive"):
            validate_show_plan(self.value)

    def test_generated_drone_ids_must_be_valid(self) -> None:
        self.value["fleet"]["drone_id_pattern"]["prefix"] = "Drone /"
        with self.assertRaisesRegex(ShowPlanValidationError, "generated index 0"):
            validate_show_plan(self.value)

    def test_role_overrides_are_unique(self) -> None:
        override = self.value["timeline"][1]["led"]["roles"][0]
        self.value["timeline"][1]["led"]["roles"].append(copy.deepcopy(override))
        with self.assertRaisesRegex(ShowPlanValidationError, "must not repeat an led_role"):
            validate_show_plan(self.value)

    def test_step_role_must_exist_when_files_are_checked(self) -> None:
        self.value["timeline"][1]["led"]["roles"][0]["led_role"] = "missing-role"
        with self.assertRaisesRegex(ShowPlanValidationError, "roles not present in Formation"):
            validate_show_plan(self.value, base_directory=PLAN_PATH.parent)

    def test_formation_hash_is_checked(self) -> None:
        self.value["formations"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ShowPlanValidationError, "does not match"):
            validate_show_plan(self.value, base_directory=PLAN_PATH.parent)

    def test_formation_point_count_must_match_fleet(self) -> None:
        self.value["fleet"]["drone_count"] = 127
        with self.assertRaisesRegex(ShowPlanValidationError, "fleet requires 127"):
            validate_show_plan(self.value, base_directory=PLAN_PATH.parent)

    def test_formation_path_must_be_relative(self) -> None:
        self.value["formations"][0]["path"] = "/tmp/formation.json"
        with self.assertRaisesRegex(ShowPlanValidationError, "must be relative"):
            validate_show_plan(self.value)

    def test_v01_led_effect_is_steady(self) -> None:
        self.value["defaults"]["led"]["default"]["effect"] = "blink"
        with self.assertRaisesRegex(ShowPlanValidationError, "supports only 'steady'"):
            validate_show_plan(self.value)


if __name__ == "__main__":
    unittest.main()
