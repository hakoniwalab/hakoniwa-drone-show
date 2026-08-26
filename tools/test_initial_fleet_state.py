from __future__ import annotations

import copy
import unittest

from tools.initial_fleet_state import (
    InitialFleetStateValidationError,
    generate_grid,
    validate_initial_fleet_state,
)


class InitialFleetStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.value = generate_grid(
            drone_count=4,
            prefix="Drone-",
            start=1,
            zero_padding=0,
            spacing_m=2.0,
            altitude_m=0.0,
            columns=2,
        )

    def test_grid_is_centered_and_ordered(self) -> None:
        self.assertEqual(
            [state["drone_id"] for state in self.value["states"]],
            ["Drone-1", "Drone-2", "Drone-3", "Drone-4"],
        )
        self.assertEqual(self.value["states"][0]["position_m"], [-1.0, 1.0, 0.0])
        self.assertEqual(self.value["states"][-1]["position_m"], [1.0, -1.0, 0.0])

    def test_generated_state_is_valid(self) -> None:
        self.assertIs(validate_initial_fleet_state(self.value), self.value)

    def test_ids_must_be_unique(self) -> None:
        self.value["states"][1]["drone_id"] = self.value["states"][0]["drone_id"]
        with self.assertRaisesRegex(InitialFleetStateValidationError, "must not repeat"):
            validate_initial_fleet_state(self.value)

    def test_led_is_validated(self) -> None:
        value = copy.deepcopy(self.value)
        value["states"][0]["led"]["brightness"] = 1.1
        with self.assertRaisesRegex(InitialFleetStateValidationError, "within"):
            validate_initial_fleet_state(value)

    def test_generator_rejects_invalid_numbering(self) -> None:
        with self.assertRaisesRegex(InitialFleetStateValidationError, "--start"):
            generate_grid(
                drone_count=1,
                prefix="Drone-",
                start=-1,
                zero_padding=0,
                spacing_m=1.0,
                altitude_m=0.0,
            )


if __name__ == "__main__":
    unittest.main()
