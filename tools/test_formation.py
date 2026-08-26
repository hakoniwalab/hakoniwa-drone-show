from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.formation import FormationValidationError, validate_formation


ROOT = Path(__file__).resolve().parents[1]


class FormationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.value = json.loads(
            (ROOT / "examples" / "formations" / "diamond-4.json").read_text(
                encoding="utf-8"
            )
        )

    def test_example_is_valid(self) -> None:
        self.assertIs(validate_formation(self.value), self.value)

    def test_drone_assignment_is_not_a_formation_field(self) -> None:
        self.value["points"][0]["drone_id"] = "Drone-1"
        with self.assertRaisesRegex(FormationValidationError, "unknown fields: drone_id"):
            validate_formation(self.value)

    def test_point_ids_are_unique(self) -> None:
        self.value["points"][1]["point_id"] = self.value["points"][0]["point_id"]
        with self.assertRaisesRegex(FormationValidationError, "point_id values must be unique"):
            validate_formation(self.value)

    def test_coordinates_are_normalized(self) -> None:
        self.value["points"][0]["position"][1] = 0.8
        self.value["points"][2]["position"][1] = -0.8
        with self.assertRaisesRegex(FormationValidationError, r"within \[-0.5, 0.5\]"):
            validate_formation(self.value)

    def test_bounding_box_is_centered(self) -> None:
        for point in self.value["points"]:
            point["position"][0] += 0.1
        with self.assertRaisesRegex(FormationValidationError, "centered at 0"):
            validate_formation(self.value)

    def test_default_led_is_optional(self) -> None:
        del self.value["points"][0]["default_led"]
        validate_formation(self.value)

    def test_default_led_is_checked_when_present(self) -> None:
        self.value["points"][0]["default_led"]["brightness"] = 1.5
        with self.assertRaisesRegex(FormationValidationError, r"within \[0, 1\]"):
            validate_formation(self.value)


if __name__ == "__main__":
    unittest.main()
