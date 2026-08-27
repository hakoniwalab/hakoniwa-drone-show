from __future__ import annotations

import unittest
from types import SimpleNamespace

from tools.global_wind_fanout import (
    GlobalWindAssetRuntime,
    GlobalWindFanout,
    NEUTRAL_SEA_LEVEL_ATM,
    NEUTRAL_TEMPERATURE_C,
)


class FakeManager:
    def __init__(self) -> None:
        self.writes = []
        self.events = []

    def run_nowait(self):
        self.events.append("run_nowait")
        return True

    def flush_pdu_raw_data_nowait(self, robot, pdu, payload):
        self.events.append(f"write:{robot}")
        self.writes.append((robot, pdu, payload))
        return True


def disturbance():
    return SimpleNamespace(
        d_temp=SimpleNamespace(value=0.0),
        d_atm=SimpleNamespace(sea_level_atm=0.0),
        d_wind=SimpleNamespace(
            value=SimpleNamespace(x=0.0, y=0.0, z=0.0)
        ),
    )


def encode(value):
    return (
        value.d_temp.value,
        value.d_atm.sea_level_atm,
        value.d_wind.value.x,
        value.d_wind.value.y,
        value.d_wind.value.z,
    )


def command(sequence, vector, *, enabled=True):
    return {
        "schema": "hakoniwa.drone-show/global-wind/v1",
        "publisher_id": "browser-a",
        "sequence": sequence,
        "source": {"mode": "manual", "provider": None, "observed_at": None},
        "wind": {"enabled": enabled, "vector_ros_m_s": list(vector)},
    }


class GlobalWindFanoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = FakeManager()
        self.fanout = GlobalWindFanout(
            manager=self.manager,
            drone_names=("Drone-1", "Drone-2"),
            disturbance_factory=disturbance,
            disturbance_encoder=encode,
        )

    def test_initializes_one_neutral_pdu_per_drone(self) -> None:
        result = self.fanout.initialize_default()
        self.assertEqual(result.drone_count, 2)
        self.assertEqual(len(self.manager.writes), 2)
        for _, pdu_name, payload in self.manager.writes:
            self.assertEqual(pdu_name, "disturb")
            self.assertEqual(
                payload,
                (NEUTRAL_TEMPERATURE_C, NEUTRAL_SEA_LEVEL_ATM, 0.0, 0.0, 0.0),
            )

    def test_changed_wind_fans_out_once_and_duplicate_does_not_write(self) -> None:
        self.fanout.initialize_default()
        changed = self.fanout.accept(command(1, (3, 4, 5)))
        duplicate = self.fanout.accept(command(2, (3, 4, 5)))
        self.assertTrue(changed.changed)
        self.assertEqual(changed.drone_count, 2)
        self.assertFalse(duplicate.changed)
        self.assertEqual(len(self.manager.writes), 4)
        self.assertEqual(self.manager.writes[-1][2][2:], (3.0, 4.0, 5.0))

    def test_reset_reapplies_current_wind_once(self) -> None:
        self.fanout.accept(command(1, (1, 2, 0)))
        before = len(self.manager.writes)
        result = self.fanout.reapply_current()
        self.assertEqual(result.drone_count, 2)
        self.assertEqual(len(self.manager.writes) - before, 2)

    def test_asset_initialization_loads_shm_before_writes_and_callback(self) -> None:
        endpoint = SimpleNamespace(
            post_start=lambda: self.manager.events.append("post_start")
        )
        runtime = GlobalWindAssetRuntime(
            manager=self.manager, fanout=self.fanout, endpoint=endpoint
        )
        runtime.initialize()
        self.assertEqual(
            self.manager.events,
            ["run_nowait", "write:Drone-1", "write:Drone-2", "post_start"],
        )


if __name__ == "__main__":
    unittest.main()
