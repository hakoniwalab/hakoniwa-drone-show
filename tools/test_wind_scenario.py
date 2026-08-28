from __future__ import annotations

from pathlib import Path
import unittest

from tools import show_control_protocol
from tools.wind_scenario import (
    WindScenarioError,
    WindScenarioPlayer,
    load_wind_scenario,
    validate_wind_scenario,
)


RUN_ID = "1" * 32
SHOW_HASH = "a" * 64


def scenario():
    return {
        "schema_version": 1,
        "scenario_id": "gust-east",
        "seed": 12345,
        "events": [
            {"time_sec": 0, "enabled": True, "speed_m_s": 0, "direction_to_deg": 90},
            {"time_sec": 1, "enabled": True, "speed_m_s": 4, "direction_to_deg": 90},
            {"time_sec": 2, "enabled": True, "speed_m_s": 8, "direction_to_deg": 180},
        ],
        "vehicle_variation": {"type": "fixed_gain", "speed_stddev_m_s": 0.32},
    }


def status(sequence: int, show_time_usec: int | None, *, run_id: str = RUN_ID):
    return show_control_protocol.show_status(
        state="running",
        run_id=run_id,
        show_sha256=SHOW_HASH,
        sequence=sequence,
        simulation_time_usec=10_000_000 + sequence,
        show_time_usec=show_time_usec,
    )


class WindScenarioTest(unittest.TestCase):
    def test_repository_example_is_valid(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "wind-scenarios"
            / "osaka-gust-east.json"
        )
        loaded = load_wind_scenario(path)
        self.assertEqual(loaded["scenario_id"], "osaka-gust-east")

    def test_requires_zero_start_and_strict_event_order(self) -> None:
        value = scenario()
        value["events"][0]["time_sec"] = 0.5
        with self.assertRaisesRegex(WindScenarioError, "first event"):
            validate_wind_scenario(value)
        value = scenario()
        value["events"][2]["time_sec"] = 1
        with self.assertRaisesRegex(WindScenarioError, "strictly increasing"):
            validate_wind_scenario(value)

    def test_waits_until_show_time_is_available(self) -> None:
        player = WindScenarioPlayer(scenario())
        self.assertEqual(player.observe_status(status(1, None)), [])
        commands = player.observe_status(status(2, 0))
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0]["wind"]["vector_ros_m_s"], [0.0, 0.0, 0.0])

    def test_applies_every_crossed_event_once(self) -> None:
        player = WindScenarioPlayer(scenario())
        commands = player.observe_status(status(1, 1_500_000))
        self.assertEqual(len(commands), 2)
        self.assertAlmostEqual(commands[-1]["wind"]["vector_ros_m_s"][0], 0.0)
        self.assertAlmostEqual(commands[-1]["wind"]["vector_ros_m_s"][1], -4.0)
        self.assertEqual(player.observe_status(status(1, 1_500_000)), [])
        commands = player.observe_status(status(2, 2_000_000))
        self.assertEqual(len(commands), 1)
        self.assertAlmostEqual(commands[0]["wind"]["vector_ros_m_s"][0], -8.0)

    def test_new_run_replays_from_zero_with_same_variation(self) -> None:
        player = WindScenarioPlayer(scenario())
        first = player.observe_status(status(1, 1_000_000))
        second = player.observe_status(status(1, 1_000_000, run_id="2" * 32))
        self.assertEqual(
            [command["wind"] for command in first],
            [command["wind"] for command in second],
        )
        self.assertNotEqual(first[0]["publisher_id"], second[0]["publisher_id"])


if __name__ == "__main__":
    unittest.main()
