from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tools.show_ir import ShowIrValidationError, validate_show_ir


ROOT = Path(__file__).resolve().parents[1]


class ShowIrTest(unittest.TestCase):
    def setUp(self) -> None:
        self.value = json.loads(
            (ROOT / "examples" / "show-ir" / "minimal.json").read_text(
                encoding="utf-8"
            )
        )

    def test_minimal_example_is_valid(self) -> None:
        self.assertIs(validate_show_ir(self.value), self.value)

    def test_timeline_must_start_at_zero(self) -> None:
        self.value["timeline"][0]["time_sec"] = 1.0
        with self.assertRaisesRegex(ShowIrValidationError, "must start at 0"):
            validate_show_ir(self.value)

    def test_timeline_must_be_strictly_increasing(self) -> None:
        self.value["timeline"][2]["time_sec"] = 5.0
        with self.assertRaisesRegex(ShowIrValidationError, "strictly increasing"):
            validate_show_ir(self.value)

    def test_every_frame_has_exact_resolved_drone_order(self) -> None:
        self.value["timeline"][1]["states"].reverse()
        with self.assertRaisesRegex(ShowIrValidationError, "exactly match"):
            validate_show_ir(self.value)

    def test_duplicate_drone_id_is_rejected(self) -> None:
        duplicate = copy.deepcopy(self.value["timeline"][0]["states"][0])
        self.value["timeline"][0]["states"].append(duplicate)
        with self.assertRaisesRegex(ShowIrValidationError, "must not repeat"):
            validate_show_ir(self.value)

    def test_led_range_is_checked_even_before_runtime_uses_it(self) -> None:
        self.value["timeline"][0]["states"][0]["led"]["rgb"][0] = 256
        with self.assertRaisesRegex(ShowIrValidationError, r"within \[0, 255\]"):
            validate_show_ir(self.value)

    def test_unknown_fields_are_rejected(self) -> None:
        self.value["vendor"] = "private-format"
        with self.assertRaisesRegex(ShowIrValidationError, "unknown fields: vendor"):
            validate_show_ir(self.value)


if __name__ == "__main__":
    unittest.main()
