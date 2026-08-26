from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import show_control_protocol as protocol
from tools.recipe import show_runtime


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class ShowRuntimeTest(unittest.TestCase):
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
                ]},
            )
            runner = root / "show_experience_runner.py"
            runner.touch()
            show_runtime.patch_launcher(
                launcher_path,
                show_runner=runner,
                drone_root=root / "drone",
                bridge_config_root=root / "bridge",
            )
            launcher = json.loads(launcher_path.read_text())
            assets = {asset["name"]: asset for asset in launcher["assets"]}
            self.assertEqual(assets["show-runner"]["args"][0], str(runner.resolve()))
            self.assertIn("--wait-for-show-start", assets["show-runner"]["args"])
            self.assertEqual(assets["show-runner"]["env"]["set"]["KEEP"], "1")
            self.assertEqual(assets["web-bridge-fleets"]["args"][1], str((root / "bridge").resolve()))
            self.assertEqual(assets["visual-state-publisher"]["args"], ["vsp.json"])


if __name__ == "__main__":
    unittest.main()
