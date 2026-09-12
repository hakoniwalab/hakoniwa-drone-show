from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT = Path(__file__).with_name("bodyframe_fleet_recording.py")
SPEC = importlib.util.spec_from_file_location("bodyframe_fleet_recording", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
recipe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recipe)


class BodyframeFleetRecordingTest(unittest.TestCase):
    def test_default_profile_is_the_selected_measurement_condition(self) -> None:
        experiment = recipe.base.resolve_experiment(recipe.DEFAULT_EXPERIMENT)
        self.assertEqual((experiment.drone_count, experiment.process_count), (128, 8))
        self.assertIsNone(experiment.measurement)
        self.assertTrue(experiment.visualization)
        self.assertTrue(experiment.show_runner_real_time_sync)
        self.assertEqual(
            (experiment.word, experiment.duration_sec, experiment.hold_sec, experiment.speed_m_s),
            ("HAKONIWA", 6.0, 0.0, 0.5),
        )

    def test_bodyframe_validation_accepts_eight_equal_partitions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config"
            type_path = config / "drone" / "fleets" / "types" / "api.json"
            type_path.parent.mkdir(parents=True)
            type_path.write_text(
                json.dumps({"components": {"droneDynamics": {"physicsEquation": "BodyFrame"}}}),
                encoding="utf-8",
            )
            for index in range(1, 9):
                path = config / "drone" / "fleets" / f"api-current-part{index}.json"
                path.write_text(
                    json.dumps({"types": {"api": "config/drone/fleets/types/api.json"}, "drones": [{}] * 16}),
                    encoding="utf-8",
                )
            errors = recipe._bodyframe_errors(
                SimpleNamespace(recipe_config=config),
                SimpleNamespace(drone_count=128, process_count=8),
            )
            self.assertEqual(errors, [])

    def test_browser_uses_the_existing_pdu_session_for_start_control(self) -> None:
        app = (recipe.SHOW_ROOT / "web" / "fleet-recording" / "recording-app.mjs").read_text(encoding="utf-8")
        self.assertIn("viewer.withPdu((pdu) => pdu)", app)
        self.assertIn("new ShowControlClient(manager, runtime, onStatus)", app)
        self.assertIn("new URL('../config/viewer-config-fleets.json', import.meta.url)", app)
        self.assertIn("renderConditions(runtime.conditions ?? {})", app)
        page = (recipe.SHOW_ROOT / "web" / "fleet-recording" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Experiment conditions", page)

    def test_viewer_url_keeps_query_parameters_out_of_the_path(self) -> None:
        url = recipe.base.viewer_url(128)
        self.assertEqual(
            url,
            "http://127.0.0.1:8000/recording/index.html?recording=1&dynamicSpawn=true"
            "&templateDroneIndex=0&maxDynamicDrones=128",
        )

    def test_orphaned_stale_session_is_removed_only_after_parent_exits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "launcher-session.json"
            session.write_text(json.dumps({"pid": 12345}), encoding="utf-8")
            with mock.patch.object(recipe.os, "kill", side_effect=ProcessLookupError):
                self.assertTrue(recipe._clear_stale_session_if_orphaned(session))
            self.assertFalse(session.exists())

            session.write_text(json.dumps({"pid": 12345}), encoding="utf-8")
            with mock.patch.object(recipe.os, "kill"):
                with self.assertRaises(recipe.base.RecipeError):
                    recipe._clear_stale_session_if_orphaned(session)
            self.assertTrue(session.exists())


if __name__ == "__main__":
    unittest.main()
