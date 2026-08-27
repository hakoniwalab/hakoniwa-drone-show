from __future__ import annotations

import argparse
import importlib.util
import io
import json
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


def write_show_definition(root: Path) -> Path:
    path = root / "show.json"
    svg = root / "face.svg"
    svg.write_bytes(
        (
            recipe.SHOW_ROOT / "assets" / "formations" / "round-ear-face.svg"
        ).read_bytes()
    )
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "show_id": "test-show",
                "formations": [
                    {
                        "formation_id": "face",
                        "svg": svg.name,
                    }
                ],
                "timeline": [
                    {
                        "step_id": "face",
                        "formation_id": "face",
                        "transition_sec": 7.0,
                        "hold_sec": 4.0,
                        "led": {"rgb": [255, 255, 255], "brightness": 1.0},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


class VirtualDroneShowTest(unittest.TestCase):
    def test_show_formation_scale_is_adapted_for_base_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_show_definition(root)
            experiment = root / "experiment.yaml"
            experiment.write_text(
                """version: 1
scenario:
  show_file: show.json
  formation:
    scale_m: 61.325
  max_speed_m_s: 20.0
""",
                encoding="utf-8",
            )
            self.assertEqual(recipe._formation_scale_m(experiment), 61.325)
            self.assertEqual(
                recipe._formation_audience_tilt_deg(experiment), 15.0
            )
            self.assertEqual(recipe._max_speed_m_s(experiment), 20.0)
            compatible = recipe._load_base_compatible_experiment(experiment)
            self.assertNotIn("formation", compatible["scenario"])
            self.assertEqual(compatible["scenario"]["type"], "hakoniwa-word")
            self.assertEqual(compatible["scenario"]["word"], "HAKONIWA")
            self.assertEqual(compatible["scenario"]["letter_width_m"], 10.0)
            self.assertEqual(compatible["scenario"]["letter_height_m"], 20.0)
            self.assertEqual(compatible["scenario"]["letter_gap_m"], 4.5)
            self.assertEqual(compatible["scenario"]["speed_m_s"], 20.0)
            self.assertEqual(compatible["scenario"]["duration_sec"], 7.0)
            self.assertEqual(compatible["scenario"]["hold_sec"], 4.0)

    def test_show_formation_scale_rejects_legacy_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_show_definition(root)
            experiment = root / "experiment.yaml"
            experiment.write_text(
                """scenario:
  show_file: show.json
  formation:
    scale_m: 15.0
  max_speed_m_s: 20.0
  letter_width_m: 10.0
""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                recipe.base.RecipeError,
                "cannot be combined with internal compatibility fields",
            ):
                recipe._load_base_compatible_experiment(experiment)

    def test_show_page_keeps_map_in_sidebar_and_threejs_full_size(self) -> None:
        page = (recipe.SHOW_ROOT / "web" / "index.html").read_text(encoding="utf-8")
        style = (recipe.SHOW_ROOT / "web" / "drone-show.css").read_text(
            encoding="utf-8"
        )
        panel_start = page.index('<aside id="show-panel">')
        panel_end = page.index("</aside>", panel_start)
        self.assertIn('<section id="map-panel"', page[panel_start:panel_end])
        self.assertNotIn('id="splitter"', page)
        self.assertIn("#three-root { width: 100%; height: 100%;", style)
        self.assertIn('id="camera-audience"', page)
        self.assertIn('id="camera-free"', page)
        self.assertIn('id="camera-state"', page)
        self.assertIn('id="camera-copy"', page)
        self.assertIn('id="camera-movement-toggle"', page)
        self.assertIn('id="camera-movement-controls"', page)
        for movement in ("forward", "backward", "left", "right", "up", "down"):
            self.assertIn(f'data-camera-move="{movement}"', page)
        self.assertIn("現在値（ENU）", page)
        app = (recipe.SHOW_ROOT / "web" / "drone-show-app.mjs").read_text(
            encoding="utf-8"
        )
        self.assertIn("getAudienceCameraState", app)
        self.assertIn("audienceCameraYaml", app)
        self.assertIn("setAudienceCameraMovementInput", app)
        self.assertIn("setCameraMovementEnabled", app)

    def test_ar_page_uses_camera_overlay_and_direction_guide(self) -> None:
        ar_root = recipe.SHOW_ROOT / "web" / "ar"
        page = (ar_root / "index.html").read_text(encoding="utf-8")
        app = (ar_root / "ar-app.mjs").read_text(encoding="utf-8")
        self.assertIn('id="camera-feed"', page)
        self.assertIn('id="three-root"', page)
        self.assertIn('id="ar-start" type="button" disabled', page)
        self.assertIn('id="direction-guide" hidden', page)
        self.assertIn('id="distance-toggle" type="button" hidden', page)
        self.assertIn('id="observer-position" hidden', page)
        self.assertIn('id="direction-arrow"', page)
        self.assertNotIn('id="ar-panel"', page)
        self.assertIn('id="movement-toggle"', page)
        for movement in ("forward", "backward", "left", "right", "up", "down"):
            self.assertIn(f'data-camera-move="{movement}"', page)
        self.assertIn("navigator.mediaDevices.getUserMedia", app)
        self.assertIn("navigator.geolocation.getCurrentPosition", app)
        self.assertIn("transparentBackground = true", app)
        self.assertIn("setAudienceCameraPose", app)
        self.assertIn("requestDeviceOrientationPermission", app)
        self.assertIn("centroidEnuFromDroneStates", app)
        self.assertIn("directionGuide", app)
        self.assertIn("smoothOrientationPose", app)
        self.assertIn("directionDistanceVisible", app)
        self.assertIn("relativeObserverPosition", app)
        self.assertIn("nearestDroneDistance", app)
        self.assertLess(
            app.index("ui.arStart.disabled = false"),
            app.index("await loadShowIr()"),
        )
        self.assertIn("await viewerReady", app)

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

    def test_default_experiment_resolves_show_scale_and_base_compatibility(self) -> None:
        formation_scale_m = recipe._formation_scale_m(recipe.DEFAULT_EXPERIMENT)
        self.assertGreater(formation_scale_m, 0.0)
        audience_tilt_deg = recipe._formation_audience_tilt_deg(
            recipe.DEFAULT_EXPERIMENT
        )
        self.assertGreaterEqual(audience_tilt_deg, -85.0)
        self.assertLessEqual(audience_tilt_deg, 85.0)
        experiment = recipe.base.resolve_experiment(recipe.DEFAULT_EXPERIMENT)
        self.assertEqual(experiment.word, "HAKONIWA")
        compatibility_scale = formation_scale_m / 61.325
        self.assertAlmostEqual(experiment.letter_width_m, 10.0 * compatibility_scale)
        self.assertAlmostEqual(experiment.letter_height_m, 20.0 * compatibility_scale)
        self.assertAlmostEqual(experiment.letter_gap_m, 4.5 * compatibility_scale)
        self.assertEqual(
            experiment.speed_m_s, recipe._max_speed_m_s(recipe.DEFAULT_EXPERIMENT)
        )
        viewer = recipe._viewer_settings(recipe.DEFAULT_EXPERIMENT)
        self.assertEqual(viewer["initial_mode"], "audience")
        self.assertEqual(viewer["network"]["host"], "192.168.11.47")
        self.assertEqual(len(viewer["audience_camera"]["position_m"]), 3)
        self.assertGreater(viewer["led_appearance"]["scale"], 0.0)
        self.assertLessEqual(viewer["led_appearance"]["scale"], 4.0)
        self.assertGreater(viewer["led_appearance"]["intensity"], 0.0)
        self.assertLessEqual(viewer["led_appearance"]["intensity"], 4.0)
        compatible = recipe._load_base_compatible_experiment(
            recipe.DEFAULT_EXPERIMENT
        )
        self.assertNotIn("viewer", compatible)
        self.assertNotIn("ar", compatible)
        ar = recipe._ar_settings(recipe.DEFAULT_EXPERIMENT)
        self.assertTrue(ar["enabled"])
        self.assertEqual(ar["preview"]["location_source"], "override")
        self.assertIsNotNone(ar["preview"]["override"])

    def test_ar_override_is_required_for_override_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            experiment = Path(temporary) / "experiment.yaml"
            experiment.write_text(
                """ar:
  enabled: true
  venue:
    latitude: 35.0
    longitude: 138.0
  preview:
    location_source: override
""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                recipe.base.RecipeError, "override is required"
            ):
                recipe._ar_settings(experiment)

    def test_audience_camera_rejects_unsupported_pitch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            experiment = Path(temporary) / "experiment.yaml"
            experiment.write_text(
                """viewer:
  initial_mode: audience
  audience_camera:
    position_m: [0, -40, 3]
    yaw_deg: 90
    pitch_deg: 90
    fov_deg: 55
""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                recipe.base.RecipeError, "pitch_deg must be between"
            ):
                recipe._viewer_settings(experiment)

    def test_led_appearance_rejects_out_of_range_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            experiment = Path(temporary) / "experiment.yaml"
            experiment.write_text(
                """viewer:
  led_appearance:
    scale: 4.1
    intensity: 1.0
""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                recipe.base.RecipeError, r"scale must be within \(0, 4\]"
            ):
                recipe._viewer_settings(experiment)

    def test_viewer_network_rejects_non_ipv4_host(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            experiment = Path(temporary) / "experiment.yaml"
            experiment.write_text(
                """viewer:
  network:
    host: http://192.168.1.10
""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                recipe.base.RecipeError, "host must be an IPv4 address"
            ):
                recipe._viewer_settings(experiment)

    def test_map_viewer_url_uses_configured_network_host(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            experiment = Path(temporary) / "experiment.yaml"
            experiment.write_text(
                """viewer:
  network:
    host: 192.168.1.23
""",
                encoding="utf-8",
            )
            self.assertTrue(
                recipe._map_viewer_url_base(experiment).startswith(
                    "http://192.168.1.23:8000/drone-show/index.html?"
                )
            )

    def test_open_viewer_always_opens_show_ui(self) -> None:
        experiment = Path("/tmp/flat-show.yaml")
        resolved = SimpleNamespace(visualization=True, drone_count=180)
        with (
            mock.patch.object(
                recipe.base, "resolve_experiment", return_value=resolved
            ),
            mock.patch.object(
                recipe,
                "_map_viewer_url_base",
                return_value=(
                    "http://127.0.0.1:8000/drone-show/index.html"
                    "?threejsRoot=/thirdparty/hakoniwa-threejs-drone"
                    "&viewerConfigName=viewer-config-fleets.json"
                ),
            ),
            mock.patch.object(recipe.base, "open_browser", return_value=True) as opened,
        ):
            self.assertEqual(recipe._open_viewer(experiment), 0)
        url = opened.call_args.args[0]
        self.assertIn("/drone-show/index.html?", url)
        self.assertIn("maxDynamicDrones=180", url)

    def test_map_viewer_url_uses_generated_marker_network_host(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            experiment = root / "resolved-experiment.yaml"
            experiment.write_text("version: 1\n", encoding="utf-8")
            recipe_config = root / "config"
            recipe_config.mkdir()
            (recipe_config / "mujoco-city-fleet.json").write_text(
                json.dumps(
                    {
                        "drone_show": {
                            "viewer": {
                                "network": {"host": "192.168.1.42"}
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            foundation = SimpleNamespace(
                resolve_workspace=mock.Mock(
                    return_value=SimpleNamespace(recipe_config=recipe_config)
                )
            )
            with mock.patch.object(
                recipe.base, "load_foundation_module", return_value=foundation
            ):
                url = recipe._map_viewer_url_base(experiment)
            self.assertTrue(
                url.startswith(
                    "http://192.168.1.42:8000/drone-show/index.html?"
                )
            )

    def test_formation_audience_tilt_rejects_out_of_range_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            experiment = Path(temporary) / "experiment.yaml"
            experiment.write_text(
                """scenario:
  formation:
    scale_m: 15
    audience_tilt_deg: 86
""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                recipe.base.RecipeError, "must be between -85 and 85"
            ):
                recipe._formation_audience_tilt_deg(experiment)

    def test_configure_requires_city_world_in_plateau_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            experiment = Path(temporary) / "plateau.yaml"
            experiment.write_text(
                "environment:\n  mode: plateau\n", encoding="utf-8"
            )
            stderr = io.StringIO()
            with (
                mock.patch.object(
                    recipe, "_require_terminated_launcher_for_configure"
                ),
                redirect_stderr(stderr),
            ):
                result = recipe.main(
                    ["configure", "--experiment", str(experiment)]
                )
            self.assertEqual(result, 2)
            self.assertIn(
                "configure requires --mujoco-city-world in plateau mode",
                stderr.getvalue(),
            )

    def test_flat_environment_resolves_ground_and_origin(self) -> None:
        settings = recipe._environment_settings(recipe.DEFAULT_EXPERIMENT)
        self.assertEqual(settings["mode"], "flat")
        self.assertAlmostEqual(
            settings["flat"]["ground_height_m"], 5.479387621660862
        )
        self.assertEqual(settings["flat"]["origin"]["latitude"], 35.0988)

    def test_configure_refuses_non_terminated_launcher_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = root / "runtime" / "launcher-session.json"
            session.parent.mkdir()
            session.write_text(
                json.dumps({"state": "RUNNING"}) + "\n", encoding="utf-8"
            )
            paths = SimpleNamespace(recipe_root=root)
            foundation = SimpleNamespace(
                resolve_workspace=mock.Mock(return_value=paths)
            )
            status = SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"state": "RUNNING"}) + "\n",
                stderr="",
            )
            with (
                mock.patch.object(
                    recipe.base, "load_foundation_module", return_value=foundation
                ),
                mock.patch.object(
                    recipe.base, "_launcher_command", return_value=["launcher-status"]
                ),
                mock.patch.object(recipe.subprocess, "run", return_value=status),
            ):
                with self.assertRaisesRegex(
                    recipe.base.RecipeError, "must be TERMINATED.*current=RUNNING"
                ):
                    recipe._require_terminated_launcher_for_configure()

    def test_configure_accepts_terminated_launcher_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = root / "runtime" / "launcher-session.json"
            session.parent.mkdir()
            session.write_text(
                json.dumps({"state": "TERMINATED"}) + "\n", encoding="utf-8"
            )
            paths = SimpleNamespace(recipe_root=root)
            foundation = SimpleNamespace(
                resolve_workspace=mock.Mock(return_value=paths)
            )
            status = SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"state": "TERMINATED"}) + "\n",
                stderr="",
            )
            with (
                mock.patch.object(
                    recipe.base, "load_foundation_module", return_value=foundation
                ),
                mock.patch.object(
                    recipe.base, "_launcher_command", return_value=["launcher-status"]
                ),
                mock.patch.object(recipe.subprocess, "run", return_value=status),
            ):
                recipe._require_terminated_launcher_for_configure()

    def test_configure_materializes_city_extension_after_base_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            experiment_path = root / "experiment.yaml"
            experiment_path.write_text(
                """viewer:
  network:
    host: 192.168.1.23
""",
                encoding="utf-8",
            )
            city_world = root / "city-world-receipt.json"
            city_world.write_text("{}\n", encoding="utf-8")
            recipe_config = root / "config"
            recipe_config.mkdir()
            launcher = recipe_config / "launcher.json"
            launcher.write_text("{}\n", encoding="utf-8")
            experiment = SimpleNamespace(
                drone_count=128, process_count=6, speed_m_s=20.0
            )
            paths = SimpleNamespace(recipe_config=recipe_config, recipe_root=root)
            foundation = SimpleNamespace(
                resolve_workspace=mock.Mock(return_value=paths)
            )
            marker = {
                "process_models": [{}] * 6,
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
                    recipe, "_formation_scale_m", return_value=15.0
                ),
                mock.patch.object(
                    recipe,
                    "_formation_audience_tilt_deg",
                    return_value=60.0,
                ),
                mock.patch.object(
                    recipe,
                    "_viewer_settings",
                    return_value={
                        "initial_mode": "free",
                        "network": {"host": "192.168.1.23"},
                    },
                ),
                mock.patch.object(
                    recipe,
                    "_show_definition",
                    return_value=(
                        recipe.SHOW_ROOT / "shows" / "three-face.show.json",
                        {
                            "timeline": [
                                {"step_id": "face-1"},
                                {"step_id": "face-2"},
                                {"step_id": "face-3"},
                            ]
                        },
                    ),
                ),
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
                mock.patch.object(
                    recipe.show_runtime, "extend_asset_pdudef"
                ) as extend_pdudef,
                mock.patch.object(
                    recipe.show_runtime,
                    "materialize_show_ir",
                    return_value=recipe_config
                    / "scenario"
                    / "show-ir"
                    / "show-ir.json",
                ) as materialize_show_ir,
                mock.patch.object(
                    recipe.show_runtime,
                    "validate_show_ir_speed_limit",
                    return_value=4.5,
                ) as validate_speed,
                redirect_stdout(io.StringIO()),
            ):
                result = recipe.configure(
                    args, experiment_path, root / "drone-pro"
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
            self.assertEqual(
                city_configure.call_args.kwargs["formation_tilt_deg"], 60.0
            )
            self.assertEqual(
                marker["drone_show"],
                {
                    "formation_scale_m": 15.0,
                    "max_speed_m_s": 20.0,
                    "viewer": {
                        "initial_mode": "free",
                        "network": {"host": "192.168.1.23"},
                    },
                    "ar": {"enabled": False},
                    "show_definition": {
                        "path": str(
                            recipe.SHOW_ROOT / "shows" / "three-face.show.json"
                        ),
                        "sha256": recipe.hashlib.sha256(
                            (
                                recipe.SHOW_ROOT
                                / "shows"
                                / "three-face.show.json"
                            ).read_bytes()
                        ).hexdigest(),
                    },
                },
            )
            viewer_access = root / "viewer-access"
            self.assertTrue((viewer_access / "viewer-qr.svg").is_file())
            self.assertIn(
                "http://192.168.1.23:8000/drone-show/index.html",
                (viewer_access / "viewer-url.txt").read_text(encoding="utf-8"),
            )
            extend_pdudef.assert_called_once_with(
                recipe_config / "pdudef" / "drone-pdudef-current.json"
            )
            materialize_show_ir.assert_called_once_with(
                recipe_config=recipe_config,
                marker=marker,
            )
            validate_speed.assert_called_once_with(
                recipe_config / "scenario" / "show-ir" / "show-ir.json",
                maximum_speed_m_s=20.0,
                initial_altitude_m=115.71,
            )

    def test_show_operator_installs_additive_launcher_hook_and_page(self) -> None:
        self.assertIs(recipe.base.write_launcher, recipe._write_show_launcher)
        self.assertIn("/drone-show/index.html", recipe.base.MAP_VIEWER_URL_BASE)

    def test_launcher_hook_keeps_show_pdudef_for_doctor_and_start(self) -> None:
        paths = SimpleNamespace(
            recipe_config=Path("/tmp/recipe-config"),
            recipe_root=Path("/tmp/recipe-root"),
        )
        with (
            mock.patch.object(
                recipe,
                "_runtime_marker_path",
                return_value=Path("/tmp/mujoco-city-fleet.json"),
            ),
            mock.patch.object(
                recipe.json,
                "loads",
                return_value={"backend": "mujoco-city"},
            ),
            mock.patch.object(Path, "read_text", return_value="{}"),
            mock.patch.object(
                recipe, "_BASE_WRITE_LAUNCHER", return_value=Path("/tmp/launcher.json")
            ),
            mock.patch.object(recipe.show_runtime, "extend_asset_pdudef") as extend,
            mock.patch.object(
                recipe.base,
                "bridge_config_root",
                return_value=Path("/tmp/base-bridge"),
            ),
            mock.patch.object(
                recipe.show_runtime,
                "materialize_bridge_config",
                return_value=Path("/tmp/bridge"),
            ),
            mock.patch.object(
                recipe.show_runtime, "materialize_browser"
            ) as materialize_browser,
            mock.patch.object(
                recipe.show_runtime,
                "patch_launcher",
                return_value=Path("/tmp/launcher.json"),
            ) as patch_launcher,
        ):
            result = recipe._write_show_launcher(
                paths,
                Path("/tmp/drone"),
                Path("/tmp/viewer"),
                SimpleNamespace(visualization=True, speed_m_s=20.0),
                "test-system",
            )
        self.assertEqual(result, Path("/tmp/launcher.json"))
        extend.assert_called_once_with(
            Path("/tmp/recipe-config/pdudef/drone-pdudef-current.json")
        )
        self.assertNotIn(
            "show_ir_max_speed_m_s", materialize_browser.call_args.kwargs
        )
        self.assertEqual(
            patch_launcher.call_args.kwargs["show_ir_max_speed_m_s"], 20.0
        )


if __name__ == "__main__":
    unittest.main()
