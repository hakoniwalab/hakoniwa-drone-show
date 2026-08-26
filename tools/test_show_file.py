from __future__ import annotations

import copy
import unittest
from pathlib import Path

from tools.show_file import ShowFileError, load_show_file, validate_show_file
from tools.svg_to_formation import convert_svg


SOURCE = Path(__file__).resolve().parents[1] / "shows" / "three-face.show.json"
KIDS_SHOW = (
    Path(__file__).resolve().parents[1]
    / "shows"
    / "kids-space-adventure.show.json"
)


class ShowFileTest(unittest.TestCase):
    def test_repository_show_is_drone_count_independent_and_valid(self) -> None:
        value = load_show_file(SOURCE)
        self.assertEqual(value["show_id"], "three-face-show")
        self.assertEqual(len(value["formations"]), 3)
        self.assertEqual(len(value["timeline"]), 3)
        self.assertNotIn("drone_count", value)
        for formation in value["formations"]:
            self.assertTrue((SOURCE.parent / formation["svg"]).resolve().is_file())

    def test_timeline_must_reference_a_declared_formation(self) -> None:
        value = load_show_file(SOURCE)
        invalid = copy.deepcopy(value)
        invalid["timeline"][0]["formation_id"] = "missing"
        with self.assertRaisesRegex(ShowFileError, "does not reference"):
            validate_show_file(invalid)

    def test_led_values_are_validated(self) -> None:
        value = load_show_file(SOURCE)
        invalid = copy.deepcopy(value)
        invalid["timeline"][0]["led"]["default"]["rgb"][1] = 256
        with self.assertRaisesRegex(ShowFileError, r"within \[0, 255\]"):
            validate_show_file(invalid)

    def test_compact_led_state_is_normalized_as_default(self) -> None:
        value = load_show_file(SOURCE)
        self.assertEqual(
            value["timeline"][0]["led"],
            {
                "default": {
                    "effect": "steady",
                    "rgb": [255, 64, 96],
                    "brightness": 1.0,
                },
                "roles": {},
            },
        )

    def test_kids_show_has_five_formations_convertible_to_180_drones(self) -> None:
        value = load_show_file(KIDS_SHOW)
        self.assertEqual(value["show_id"], "kids-space-adventure")
        self.assertEqual(len(value["formations"]), 5)
        self.assertEqual(len(value["timeline"]), 5)
        for formation in value["formations"]:
            document = convert_svg(
                (KIDS_SHOW.parent / formation["svg"]).resolve(),
                formation_id=f"{formation['formation_id']}-180",
                point_count=180,
            )
            self.assertEqual(len(document["points"]), 180)
            available_roles = {point["led_role"] for point in document["points"]}
            used_roles = {
                role
                for step in value["timeline"]
                if step["formation_id"] == formation["formation_id"]
                for role in step["led"]["roles"]
            }
            self.assertLessEqual(used_roles, available_roles)


if __name__ == "__main__":
    unittest.main()
