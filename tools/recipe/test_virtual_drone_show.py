from __future__ import annotations

import argparse
import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT = Path(__file__).with_name("virtual_drone_show.py")
SPEC = importlib.util.spec_from_file_location("virtual_drone_show", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
recipe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = recipe
SPEC.loader.exec_module(recipe)


class VirtualDroneShowTest(unittest.TestCase):
    def test_default_sources_use_sibling_repositories(self) -> None:
        self.assertEqual(
            recipe.BUSINESS_PACK_ROOT,
            (recipe.SHOW_ROOT.parent / "hakoniwa-business-pack").resolve(),
        )
        self.assertEqual(
            recipe._drone_root("configure", None),
            (recipe.SHOW_ROOT.parent / "hakoniwa-drone-pro").resolve(),
        )
        self.assertEqual(
            recipe._viewer_root(None),
            (recipe.SHOW_ROOT.parent / "hakoniwa-threejs-drone").resolve(),
        )

    def test_configure_requires_city_world(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = recipe.main(["configure"])
        self.assertEqual(result, 2)
        self.assertIn("configure requires --mujoco-city-world", stderr.getvalue())

    def test_configure_materializes_city_extension_after_base_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            city_world = root / "city-world-receipt.json"
            city_world.write_text("{}\n", encoding="utf-8")
            recipe_config = root / "config"
            recipe_config.mkdir()
            launcher = recipe_config / "launcher.json"
            launcher.write_text("{}\n", encoding="utf-8")
            experiment = SimpleNamespace(drone_count=128, process_count=6)
            paths = SimpleNamespace(recipe_config=recipe_config)
            foundation = SimpleNamespace(
                resolve_workspace=mock.Mock(return_value=paths)
            )
            marker = {
                "process_models": [object()] * 6,
                "flight_plan": {
                    "show_phases": ["CHIIKAWA", "HACHIWARE", "USAGI"],
                    "resolved_flight_altitude_m": 115.71,
                },
            }
            args = argparse.Namespace(
                mujoco_city_world=city_world,
                drone_count=128,
                process_count=6,
                formation_scale=None,
                spawn_altitude_m=0.2,
                spawn_spacing_m=1.0,
                altitude_mode="city-max-clearance",
                above_city_clearance_m=10.0,
                formation_rotation_deg=90.0,
                formation_tilt_deg=15.0,
            )
            with (
                mock.patch.object(
                    recipe.base, "configure", return_value=0
                ) as base_configure,
                mock.patch.object(
                    recipe.base, "resolve_experiment", return_value=experiment
                ),
                mock.patch.object(
                    recipe.base, "load_foundation_module", return_value=foundation
                ),
                mock.patch.object(
                    recipe.city,
                    "configure_single_host_fleet",
                    return_value=marker,
                ) as city_configure,
                redirect_stdout(io.StringIO()),
            ):
                result = recipe.configure(
                    args, root / "experiment.yaml", root / "drone-pro"
                )

            self.assertEqual(result, 0)
            base_configure.assert_called_once()
            city_configure.assert_called_once()
            self.assertFalse(launcher.exists())
            self.assertEqual(
                city_configure.call_args.kwargs["recipe_config"], recipe_config
            )
            self.assertEqual(city_configure.call_args.kwargs["drone_count"], 128)
            self.assertEqual(city_configure.call_args.kwargs["process_count"], 6)


if __name__ == "__main__":
    unittest.main()
