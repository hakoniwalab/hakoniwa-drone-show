from __future__ import annotations

import copy
import unittest
from pathlib import Path

from tools.show_file import ShowFileError, load_show_file, validate_show_file


SOURCE = Path(__file__).resolve().parents[1] / "shows" / "three-face.show.json"


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
        invalid["timeline"][0]["led"]["rgb"][1] = 256
        with self.assertRaisesRegex(ShowFileError, r"within \[0, 255\]"):
            validate_show_file(invalid)


if __name__ == "__main__":
    unittest.main()
