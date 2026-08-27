from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import show_control_protocol as protocol
from tools.recipe import show_runtime


SHOW_DEFINITION = (
    Path(__file__).resolve().parents[2] / "shows" / "three-face.show.json"
)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class ShowRuntimeTest(unittest.TestCase):
    def test_signed_audience_tilt_keeps_formation_side(self) -> None:
        self.assertEqual(show_runtime._show_plan_tilt_from_audience(60.0), 30.0)
        self.assertEqual(show_runtime._show_plan_tilt_from_audience(-60.0), -30.0)
        self.assertEqual(show_runtime._show_plan_tilt_from_audience(0.0), 90.0)

    def test_asset_pdudef_extension_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdu = root / "pdudef.json"
            write_json(
                pdu,
                {
                    "paths": [{"id": "drone", "path": "drone.json"}],
                    "robots": [{"name": "Drone-1", "pdutypes_id": "drone"}],
                },
            )
            show_runtime.extend_asset_pdudef(pdu)
            show_runtime.extend_asset_pdudef(pdu)
            value = json.loads(pdu.read_text())
            self.assertEqual(
                [entry["name"] for entry in value["robots"]].count(protocol.ROBOT_NAME),
                1,
            )
            types = json.loads((root / show_runtime.SHOW_PDUTYPES_FILE).read_text())
            self.assertEqual([entry["pdu_size"] for entry in types], [1024, 1024])

    def test_bridge_adds_bidirectional_show_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "base"
            write_json(
                base / "bridge" / "bridge.json",
                {
                    "version": "2.0.0",
                    "transferPolicies": {"ticker": {"type": "ticker", "intervalMs": 20}},
                    "nodes": [{"id": "web_bridge_fleets_node1"}],
                    "pduKeyGroups": {},
                    "connections": [],
                },
            )
            write_json(
                base / "endpoint" / "endpoint_container.json",
                [{"nodeId": "web_bridge_fleets_node1", "endpoints": [
                    {"id": "bridge-shm-ep", "direction": "in", "config_path": "visual-state-shm.json"},
                    {"id": "bridge-ws-ep", "direction": "out", "config_path": "visual-state-ws.json"},
                ]}],
            )
            write_json(base / "endpoint" / "visual-state-shm.json", {"pdu_def_path": "../pdu/drone-visual-state.json"})
            write_json(base / "endpoint" / "visual-state-ws.json", {"pdu_def_path": "../pdu/drone-visual-state.json"})
            write_json(
                base / "pdu" / "drone-visual-state.json",
                {"paths": [{"id": "visual", "path": "visual.json"}], "robots": [{"name": "VSP", "pdutypes_id": "visual"}]},
            )
            write_json(
                base / "comm" / "visual-state-shm-callback.json",
                {"io": {"robots": [{"name": "VSP", "pdu": []}]}},
            )
            output = show_runtime.materialize_bridge_config(base, root / "output")
            bridge = json.loads((output / "bridge" / "bridge.json").read_text())
            self.assertIn("drone_show_command", bridge["pduKeyGroups"])
            self.assertIn("drone_show_status", bridge["pduKeyGroups"])
            self.assertEqual(
                {entry["id"] for entry in bridge["connections"]},
                {"conn_drone_show_command_ws_to_shm", "conn_drone_show_status_shm_to_ws"},
            )
            container = json.loads((output / "endpoint" / "endpoint_container.json").read_text())
            self.assertEqual(
                {entry["direction"] for entry in container[0]["endpoints"]},
                {"inout"},
            )
            shm = json.loads((output / "comm" / "visual-state-shm-callback.json").read_text())
            show = next(item for item in shm["io"]["robots"] if item["name"] == protocol.ROBOT_NAME)
            self.assertEqual(show["pdu"][1]["notify_on_recv"], True)

    def test_launcher_is_patched_without_changing_other_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launcher_path = root / "launcher.json"
            write_json(
                launcher_path,
                {"assets": [
                    {"name": "show-runner", "args": ["old.py", "--show-json", "show.json"], "env": {"set": {"KEEP": "1"}}},
                    {"name": "web-bridge-fleets", "args": ["--config-root", "old", "--node-name", "node"]},
                    {"name": "visual-state-publisher", "args": ["vsp.json"]},
                    {"name": "threejs-viewer-webserver", "args": ["-m", "http.server", "8000"]},
                ]},
            )
            runner = root / "show_experience_runner.py"
            runner.touch()
            show_ir = root / "show-ir.json"
            show_ir.touch()
            no_cache_server = root / "no_cache_http_server.py"
            no_cache_server.touch()
            show_runtime.patch_launcher(
                launcher_path,
                show_runner=runner,
                drone_root=root / "drone",
                bridge_config_root=root / "bridge",
                no_cache_http_server=no_cache_server,
                show_ir_path=show_ir,
                show_ir_max_speed_m_s=20.0,
            )
            launcher = json.loads(launcher_path.read_text())
            assets = {asset["name"]: asset for asset in launcher["assets"]}
            self.assertEqual(assets["show-runner"]["args"][0], str(runner.resolve()))
            self.assertIn("--wait-for-show-start", assets["show-runner"]["args"])
            ir_index = assets["show-runner"]["args"].index("--show-ir")
            self.assertEqual(
                assets["show-runner"]["args"][ir_index + 1], str(show_ir.resolve())
            )
            speed_index = assets["show-runner"]["args"].index(
                "--show-ir-max-speed-m-s"
            )
            self.assertEqual(
                assets["show-runner"]["args"][speed_index + 1], "20.0"
            )
            self.assertEqual(assets["show-runner"]["env"]["set"]["KEEP"], "1")
            self.assertEqual(
                assets["threejs-viewer-webserver"]["args"],
                [str(no_cache_server.resolve()), "8000"],
            )
            self.assertEqual(assets["web-bridge-fleets"]["args"][1], str((root / "bridge").resolve()))
            self.assertEqual(assets["visual-state-publisher"]["args"], ["vsp.json"])

    def test_launcher_adds_ar_https_and_wss_gateway(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launcher_path = root / "launcher.json"
            write_json(
                launcher_path,
                {"assets": [
                    {"name": "show-runner", "args": ["old.py"], "env": {"set": {}}},
                    {"name": "web-bridge-fleets", "args": ["--config-root", "old"]},
                    {"name": "threejs-viewer-webserver", "command": "python3", "args": [], "cwd": str(root / "web")},
                ]},
            )
            runner = root / "runner.py"
            gateway = root / "gateway.py"
            certificate = root / "server.crt"
            private_key = root / "server.key"
            for path in (runner, gateway, certificate, private_key):
                path.touch()
            show_runtime.patch_launcher(
                launcher_path,
                show_runner=runner,
                drone_root=root / "drone",
                bridge_config_root=root / "bridge",
                ar_gateway=gateway,
                ar_certificate=certificate,
                ar_private_key=private_key,
            )
            assets = {
                asset["name"]: asset
                for asset in json.loads(launcher_path.read_text())["assets"]
            }
            ar = assets["ar-https-gateway"]
            self.assertEqual(ar["command"], "python3")
            self.assertEqual(ar["cwd"], str(root / "web"))
            self.assertIn("8443", ar["args"])
            self.assertIn("8766", ar["args"])

    def test_show_ir_speed_limit_is_validated_against_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            show_ir = Path(temporary) / "show-ir.json"
            write_json(
                show_ir,
                {
                    "timeline": [
                        {
                            "time_sec": 0.0,
                            "states": [
                                {"drone_id": "Drone-1", "position_m": [0, 0, 0]}
                            ],
                        },
                        {
                            "time_sec": 2.0,
                            "states": [
                                {"drone_id": "Drone-1", "position_m": [3, 4, 10]}
                            ],
                        },
                        {
                            "time_sec": 12.0,
                            "states": [
                                {"drone_id": "Drone-1", "position_m": [3, 4, 10]}
                            ],
                        },
                    ]
                },
            )
            self.assertEqual(
                show_runtime.validate_show_ir_speed_limit(
                    show_ir,
                    maximum_speed_m_s=3.0,
                    initial_altitude_m=10.0,
                ),
                2.5,
            )
            with self.assertRaisesRegex(
                show_runtime.ShowRuntimeError, "required=2.500.*maximum=2.000"
            ):
                show_runtime.validate_show_ir_speed_limit(
                    show_ir,
                    maximum_speed_m_s=2.0,
                    initial_altitude_m=10.0,
                )

    def test_browser_receives_the_exact_runtime_show_ir(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            show_root = root / "show"
            write_json(show_root / "web" / "placeholder.json", {"ok": True})
            web_root = root / "viewer"
            embedded = web_root / "thirdparty" / "hakoniwa-threejs-drone"
            write_json(
                embedded / "config" / "viewer-config-fleets.json",
                {
                    "pdu": {"pduDefPath": "./visual.json"},
                },
            )
            write_json(
                embedded / "config" / "visual.json",
                {"paths": [], "robots": []},
            )
            marker = root / "marker.json"
            write_json(
                marker,
                {
                    "backend": "mujoco-city",
                    "drone_count": 2,
                    "flight_plan": {"altitude_reference_height_m": 13.8},
                    "drone_show": {
                        "viewer": {
                            "network": {"host": "192.168.1.23"},
                            "initial_mode": "audience",
                            "audience_camera": {
                                "position_m": [0.0, -40.0, 3.0],
                                "yaw_deg": 90.0,
                                "pitch_deg": 35.0,
                                "fov_deg": 55.0,
                            },
                            "led_appearance": {
                                "scale": 2.0,
                                "intensity": 1.75,
                            },
                            "city_lighting": {
                                "enabled": True,
                                "brightness": 1.4,
                                "lights": [{
                                    "enabled": True,
                                    "position_m": [1.0, -20.0, 7.0],
                                    "target_m": [1.0, 2.0, 24.0],
                                    "brightness": 1.2,
                                    "spread_deg": 42.0,
                                    "color": "#ffd6a0",
                                }],
                            },
                            "crowd": {
                                "enabled": True,
                                "count": 240,
                                "center_m": [0.0, -34.0],
                                "width_m": 44.0,
                                "depth_m": 16.0,
                                "ground_height_m": 5.5,
                                "lighting": {
                                    "enabled": True,
                                    "intensity": 140.0,
                                    "height_m": 4.0,
                                },
                            },
                        },
                        "ar": {
                            "enabled": True,
                            "venue": {
                                "latitude": 35.0,
                                "longitude": 138.0,
                                "heading_deg": 0.0,
                            },
                            "preview": {
                                "location_source": "device",
                                "override": None,
                                "eye_height_m": 1.6,
                                "movement_speed_m_s": 5.0,
                                "device_orientation": "optional",
                            },
                        },
                    },
                    "city_world": {
                        "origin": {
                            "latitude": 35.0,
                            "longitude": 138.0,
                            "altitude_offset_m": 0.0,
                        }
                    },
                },
            )
            show_ir = root / "show-ir.json"
            show_ir.write_text('{"schema_version":"0.1"}\n', encoding="utf-8")

            destination = show_runtime.materialize_browser(
                show_root=show_root,
                web_root=web_root,
                marker_path=marker,
                show_ir_path=show_ir,
            )

            self.assertEqual((destination / "show-ir.json").read_bytes(), show_ir.read_bytes())
            runtime = json.loads((destination / "runtime-config.json").read_text())
            viewer = json.loads(
                (
                    embedded / "config" / "viewer-config-fleets.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                viewer["three"]["droneAppearance"],
                {"bodyColor": "#E8EDF2"},
            )
            self.assertEqual(viewer["three"]["initialCameraMode"], "audience")
            self.assertEqual(
                viewer["three"]["audienceCamera"],
                {
                    "positionM": [0.0, -40.0, 3.0],
                    "yawDeg": 90.0,
                    "pitchDeg": 35.0,
                    "fovDeg": 55.0,
                },
            )
            self.assertEqual(
                runtime["led_appearance"],
                {
                    "scale": 2.0,
                    "intensity": 1.75,
                    "spatialDepthCue": False,
                },
            )
            self.assertTrue(runtime["ar"]["enabled"])
            self.assertEqual(runtime["ar"]["ground_height_m"], 13.8)
            self.assertEqual(
                runtime["ar"]["secure_websocket_url"],
                "wss://192.168.1.23:8443/pdu",
            )
            self.assertEqual(
                runtime["camera"],
                {"initial_mode": "audience", "audience_available": True},
            )
            self.assertEqual(
                runtime["city_lighting"],
                {
                    "enabled": True,
                    "brightness": 1.4,
                    "lights": [{
                        "enabled": True,
                        "position_m": [1.0, -20.0, 7.0],
                        "target_m": [1.0, 2.0, 24.0],
                        "brightness": 1.2,
                        "spread_deg": 42.0,
                        "color": "#ffd6a0",
                    }],
                },
            )
            self.assertEqual(
                runtime["crowd"],
                {
                    "enabled": True,
                    "count": 240,
                    "center_m": [0.0, -34.0],
                    "width_m": 44.0,
                    "depth_m": 16.0,
                    "ground_height_m": 5.5,
                    "lighting": {
                        "enabled": True,
                        "intensity": 140.0,
                        "height_m": 4.0,
                    },
                },
            )
            self.assertEqual(
                runtime["websocket_url"], "ws://192.168.1.23:8765"
            )
            self.assertEqual(runtime["show_ir"]["url"], "./show-ir.json")
            self.assertEqual(
                runtime["show_ir"]["sha256"], show_runtime._sha256(show_ir)
            )

    def test_flat_viewer_has_no_city_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            viewer = root / "hakoniwa-threejs-drone"
            (viewer / "src").mkdir(parents=True)
            (viewer / "assets").mkdir()
            (viewer / "thirdparty").mkdir()
            (viewer / "config").mkdir()
            (viewer / "index.html").write_text("viewer", encoding="utf-8")
            write_json(
                viewer / "config" / "drone_config-compact-1.json",
                {"environments": [{"name": "old-city"}]},
            )
            write_json(
                viewer / "config" / "viewer-config-fleets.json",
                {"three": {}, "stateInput": {"fleets": {}}},
            )
            map_viewer = root / "hakoniwa-map-viewer"
            (map_viewer / "src" / "client").mkdir(parents=True)
            (map_viewer / "images").mkdir()
            (map_viewer / "src" / "client" / "frame.js").write_text(
                "export {};", encoding="utf-8"
            )
            marker = root / "flat-marker.json"
            write_json(marker, {"backend": "mujoco-flat", "drone_count": 180})
            web_root = show_runtime.materialize_flat_viewer(
                viewer_root=viewer,
                web_root=root / "web",
                marker_path=marker,
            )
            embedded = web_root / "thirdparty" / "hakoniwa-threejs-drone"
            scene = json.loads(
                (embedded / "config" / "drone_config-flat-fleet.json").read_text()
            )
            config = json.loads(
                (embedded / "config" / "viewer-config-fleets.json").read_text()
            )
            self.assertEqual(scene["environments"], [])
            self.assertEqual(
                config["three"]["sceneConfigPath"],
                "./drone_config-flat-fleet.json",
            )
            self.assertEqual(
                config["stateInput"]["fleets"]["maxDynamicDrones"], 180
            )

    def test_configured_city_fleet_is_compiled_into_show_ir(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recipe_config = root / "config"
            fleet_path = recipe_config / "drone" / "fleets" / "api-current.json"
            drones = [
                {
                    "name": f"Drone-{index}",
                    "position_meter": [float(index), 2.0, -3.0],
                }
                for index in range(1, 33)
            ]
            write_json(fleet_path, {"drones": drones})
            show_ir_path = show_runtime.materialize_show_ir(
                recipe_config=recipe_config,
                marker={
                    "drone_count": 32,
                    "fleet_config": str(fleet_path),
                    "drone_show": {
                        "formation_scale_m": 15.0,
                        "formation_depth_m": 3.0,
                        "show_definition": {
                            "path": str(SHOW_DEFINITION),
                            "sha256": show_runtime._sha256(SHOW_DEFINITION),
                        },
                    },
                    "flight_plan": {
                        "resolved_flight_altitude_m": 50.0,
                        "formation_audience_tilt_deg": 60.0,
                    },
                },
            )
            show_ir = json.loads(show_ir_path.read_text(encoding="utf-8"))
            self.assertEqual(show_ir["drone_ids"], [f"Drone-{i}" for i in range(1, 33)])
            self.assertEqual(
                [frame["time_sec"] for frame in show_ir["timeline"]],
                [0.0, 6.0, 16.0, 22.0, 32.0, 38.0, 48.0],
            )
            self.assertEqual(
                show_ir["timeline"][0]["states"][0]["position_m"],
                [2.0, 1.0, 3.0],
            )
            self.assertEqual(
                [
                    show_ir["timeline"][index]["states"][0]["led"]["rgb"]
                    for index in (1, 3, 5)
                ],
                [[255, 64, 96], [64, 255, 128], [255, 220, 48]],
            )
            plan = json.loads(
                (show_ir_path.parent / "show-plan.json").read_text(encoding="utf-8")
            )
            self.assertEqual(plan["defaults"]["transform"]["scale_m"], 15.0)
            self.assertEqual(plan["defaults"]["transform"]["tilt_deg"], 30.0)
            self.assertEqual(plan["defaults"]["transform"]["depth_m"], 3.0)

    def test_runtime_uses_external_formation_order_and_timing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recipe_config = root / "config"
            fleet_path = recipe_config / "drone" / "fleets" / "api-current.json"
            write_json(
                fleet_path,
                {
                    "drones": [
                        {
                            "name": f"Drone-{index}",
                            "position_meter": [float(index), 0.0, -1.0],
                        }
                        for index in range(1, 33)
                    ]
                },
            )
            source_svg = (
                SHOW_DEFINITION.parent.parent
                / "assets"
                / "formations"
                / "round-ear-face.svg"
            )
            svg = root / "face.svg"
            svg.write_bytes(source_svg.read_bytes())
            definition = root / "custom-show.json"
            write_json(
                definition,
                {
                    "schema_version": "1.0",
                    "show_id": "custom-show",
                    "formations": [
                        {"formation_id": "alpha", "svg": "face.svg"},
                        {"formation_id": "beta", "svg": "face.svg"},
                    ],
                    "timeline": [
                        {
                            "step_id": "first",
                            "formation_id": "beta",
                            "transition_sec": 2.0,
                            "hold_sec": 1.0,
                            "led": {"rgb": [1, 2, 3], "brightness": 0.5},
                        },
                        {
                            "step_id": "second",
                            "formation_id": "alpha",
                            "transition_sec": 3.0,
                            "hold_sec": 4.0,
                            "led": {
                                "default": {
                                    "rgb": [4, 5, 6],
                                    "brightness": 1.0,
                                },
                                "roles": {
                                    "eyes": {
                                        "rgb": [7, 8, 9],
                                        "brightness": 0.75,
                                    }
                                },
                            },
                        },
                    ],
                },
            )
            show_ir_path = show_runtime.materialize_show_ir(
                recipe_config=recipe_config,
                marker={
                    "drone_count": 32,
                    "fleet_config": str(fleet_path),
                    "drone_show": {
                        "formation_scale_m": 10.0,
                        "show_definition": {
                            "path": str(definition),
                            "sha256": show_runtime._sha256(definition),
                        },
                    },
                    "flight_plan": {
                        "resolved_flight_altitude_m": 5.0,
                        "formation_audience_tilt_deg": 60.0,
                    },
                },
            )
            show_ir = json.loads(show_ir_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [frame["time_sec"] for frame in show_ir["timeline"]],
                [0.0, 2.0, 3.0, 6.0, 10.0],
            )
            plan = json.loads(
                (show_ir_path.parent / "show-plan.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [step["formation_id"] for step in plan["timeline"]],
                ["beta-32", "alpha-32"],
            )
            self.assertEqual(
                [step["led"]["default"]["rgb"] for step in plan["timeline"]],
                [[1, 2, 3], [4, 5, 6]],
            )
            self.assertEqual(
                plan["timeline"][1]["led"]["roles"],
                [
                    {
                        "led_role": "eyes",
                        "state": {
                            "effect": "steady",
                            "rgb": [7, 8, 9],
                            "brightness": 0.75,
                        },
                    }
                ],
            )
            alpha_colors = {
                tuple(state["led"]["rgb"])
                for state in show_ir["timeline"][3]["states"]
            }
            self.assertEqual(alpha_colors, {(4, 5, 6), (7, 8, 9)})


if __name__ == "__main__":
    unittest.main()
