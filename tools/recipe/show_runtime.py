"""Materialize Drone Show control PDUs, WebBridge routes, and browser assets."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from tools import show_control_protocol as protocol


SHOW_PDUTYPES_ID = "drone_show_control_type"
SHOW_PDUTYPES_FILE = "drone-show-control-pdutypes.json"
SHOW_BRIDGE_PDUDEF_FILE = "drone-show-visual-state.json"


class ShowRuntimeError(RuntimeError):
    pass


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShowRuntimeError(f"invalid JSON file {path}: {exc}") from exc


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def show_pdutypes() -> list[dict[str, Any]]:
    return [
        {
            "channel_id": protocol.COMMAND_CHANNEL_ID,
            "pdu_size": protocol.FRAME_SIZE,
            "name": protocol.COMMAND_PDU_NAME,
            "type": "hako_msgs/DroneShowJsonFrame",
        },
        {
            "channel_id": protocol.STATUS_CHANNEL_ID,
            "pdu_size": protocol.FRAME_SIZE,
            "name": protocol.STATUS_PDU_NAME,
            "type": "hako_msgs/DroneShowJsonFrame",
        },
    ]


def extend_asset_pdudef(pdu_def_path: Path) -> Path:
    """Add the two Show control SHM slots to a generated Drone PDU config."""

    pdu_def_path = pdu_def_path.resolve()
    root = _read_json(pdu_def_path)
    paths = root.get("paths")
    robots = root.get("robots")
    if not isinstance(paths, list) or not isinstance(robots, list):
        raise ShowRuntimeError(f"PDU definition has no paths/robots arrays: {pdu_def_path}")
    _write_json(pdu_def_path.parent / SHOW_PDUTYPES_FILE, show_pdutypes())
    root["paths"] = [
        item
        for item in paths
        if isinstance(item, dict) and item.get("id") != SHOW_PDUTYPES_ID
    ] + [{"id": SHOW_PDUTYPES_ID, "path": SHOW_PDUTYPES_FILE}]
    root["robots"] = [
        item
        for item in robots
        if isinstance(item, dict) and item.get("name") != protocol.ROBOT_NAME
    ] + [{"name": protocol.ROBOT_NAME, "pdutypes_id": SHOW_PDUTYPES_ID}]
    _write_json(pdu_def_path, root)
    return pdu_def_path


def materialize_bridge_config(base_root: Path, output_root: Path) -> Path:
    """Copy the installed fleet bridge and add Show command/status routes."""

    base_root = base_root.resolve()
    output_root = output_root.resolve()
    required = (
        base_root / "bridge" / "bridge.json",
        base_root / "endpoint" / "endpoint_container.json",
        base_root / "pdu" / "drone-visual-state.json",
    )
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise ShowRuntimeError(
            "installed fleet WebBridge config is incomplete: "
            + ", ".join(str(path) for path in missing)
        )
    shutil.copytree(base_root, output_root, dirs_exist_ok=True)

    pdu_dir = output_root / "pdu"
    _write_json(pdu_dir / SHOW_PDUTYPES_FILE, show_pdutypes())
    visual_root = _read_json(pdu_dir / "drone-visual-state.json")
    paths = visual_root.get("paths", [])
    robots = visual_root.get("robots", [])
    combined = {
        "paths": [
            item
            for item in paths
            if isinstance(item, dict) and item.get("id") != SHOW_PDUTYPES_ID
        ]
        + [{"id": SHOW_PDUTYPES_ID, "path": SHOW_PDUTYPES_FILE}],
        "robots": [
            item
            for item in robots
            if isinstance(item, dict) and item.get("name") != protocol.ROBOT_NAME
        ]
        + [{"name": protocol.ROBOT_NAME, "pdutypes_id": SHOW_PDUTYPES_ID}],
    }
    _write_json(pdu_dir / SHOW_BRIDGE_PDUDEF_FILE, combined)

    endpoint_dir = output_root / "endpoint"
    for name in ("visual-state-shm.json", "visual-state-ws.json"):
        endpoint = _read_json(endpoint_dir / name)
        endpoint["pdu_def_path"] = f"../pdu/{SHOW_BRIDGE_PDUDEF_FILE}"
        _write_json(endpoint_dir / name, endpoint)
    container = _read_json(endpoint_dir / "endpoint_container.json")
    for node in container:
        if not isinstance(node, dict):
            continue
        for endpoint in node.get("endpoints", []):
            if isinstance(endpoint, dict) and endpoint.get("id") in {
                "bridge-shm-ep",
                "bridge-ws-ep",
            }:
                endpoint["direction"] = "inout"
    _write_json(endpoint_dir / "endpoint_container.json", container)

    shm_path = output_root / "comm" / "visual-state-shm-callback.json"
    shm = _read_json(shm_path)
    robots = shm.setdefault("io", {}).setdefault("robots", [])
    robots[:] = [
        item
        for item in robots
        if isinstance(item, dict) and item.get("name") != protocol.ROBOT_NAME
    ]
    robots.append(
        {
            "name": protocol.ROBOT_NAME,
            "pdu": [
                {"name": protocol.COMMAND_PDU_NAME, "notify_on_recv": False},
                {"name": protocol.STATUS_PDU_NAME, "notify_on_recv": True},
            ],
        }
    )
    _write_json(shm_path, shm)

    bridge_path = output_root / "bridge" / "bridge.json"
    bridge = _read_json(bridge_path)
    bridge.setdefault("transferPolicies", {})["immediate"] = {"type": "immediate"}
    groups = bridge.setdefault("pduKeyGroups", {})
    groups["drone_show_command"] = [
        {
            "id": f"{protocol.ROBOT_NAME}.{protocol.COMMAND_PDU_NAME}",
            "robot_name": protocol.ROBOT_NAME,
            "pdu_name": protocol.COMMAND_PDU_NAME,
        }
    ]
    groups["drone_show_status"] = [
        {
            "id": f"{protocol.ROBOT_NAME}.{protocol.STATUS_PDU_NAME}",
            "robot_name": protocol.ROBOT_NAME,
            "pdu_name": protocol.STATUS_PDU_NAME,
        }
    ]
    connections = bridge.setdefault("connections", [])
    connections[:] = [
        item
        for item in connections
        if isinstance(item, dict)
        and item.get("id")
        not in {"conn_drone_show_command_ws_to_shm", "conn_drone_show_status_shm_to_ws"}
    ]
    node_id = bridge.get("nodes", [{}])[0].get("id", "web_bridge_fleets_node1")
    connections.extend(
        [
            {
                "id": "conn_drone_show_command_ws_to_shm",
                "nodeId": node_id,
                "source": {"endpointId": "bridge-ws-ep"},
                "destinations": [{"endpointId": "bridge-shm-ep"}],
                "transferPdus": [
                    {"pduKeyGroupId": "drone_show_command", "policyId": "immediate"}
                ],
            },
            {
                "id": "conn_drone_show_status_shm_to_ws",
                "nodeId": node_id,
                "source": {"endpointId": "bridge-shm-ep"},
                "destinations": [{"endpointId": "bridge-ws-ep"}],
                "transferPdus": [
                    {"pduKeyGroupId": "drone_show_status", "policyId": "immediate"}
                ],
            },
        ]
    )
    _write_json(bridge_path, bridge)
    return output_root


def materialize_browser(
    *,
    show_root: Path,
    web_root: Path,
    marker_path: Path,
) -> Path:
    """Install the Show-owned page beside the Recipe-local Map Viewer."""

    show_root = show_root.resolve()
    web_root = web_root.resolve()
    marker = _read_json(marker_path.resolve())
    city = marker.get("city_world")
    if not isinstance(city, dict) or not isinstance(city.get("origin"), dict):
        raise ShowRuntimeError("MuJoCo City marker has no city origin")

    embedded = web_root / "thirdparty" / "hakoniwa-threejs-drone"
    viewer_config_path = embedded / "config" / "viewer-config-fleets.json"
    viewer_config = _read_json(viewer_config_path)
    original_pdu_path = viewer_config.get("pdu", {}).get("pduDefPath")
    if not isinstance(original_pdu_path, str):
        raise ShowRuntimeError("fleet Viewer config has no pduDefPath")
    original_pdu = (viewer_config_path.parent / original_pdu_path).resolve()
    visual = _read_json(original_pdu)
    _write_json(embedded / "config" / SHOW_PDUTYPES_FILE, show_pdutypes())
    visual["paths"] = [
        item
        for item in visual.get("paths", [])
        if isinstance(item, dict) and item.get("id") != SHOW_PDUTYPES_ID
    ] + [{"id": SHOW_PDUTYPES_ID, "path": SHOW_PDUTYPES_FILE}]
    visual["robots"] = [
        item
        for item in visual.get("robots", [])
        if isinstance(item, dict) and item.get("name") != protocol.ROBOT_NAME
    ] + [{"name": protocol.ROBOT_NAME, "pdutypes_id": SHOW_PDUTYPES_ID}]
    combined_name = "pdudef-drone-show.json"
    _write_json(embedded / "config" / combined_name, visual)
    viewer_config.setdefault("pdu", {})["pduDefPath"] = f"./{combined_name}"
    _write_json(viewer_config_path, viewer_config)

    destination = web_root / "drone-show"
    shutil.copytree(show_root / "web", destination, dirs_exist_ok=True)
    runtime_config = {
        "schema_version": 1,
        "threejs_root": "/thirdparty/hakoniwa-threejs-drone",
        "viewer_config_name": "viewer-config-fleets.json",
        "websocket_url": "ws://127.0.0.1:8765",
        "origin": city["origin"],
        "expected_drone_count": int(marker["drone_count"]),
        "control": {
            "robot_name": protocol.ROBOT_NAME,
            "command_pdu_name": protocol.COMMAND_PDU_NAME,
            "status_pdu_name": protocol.STATUS_PDU_NAME,
            "frame_size": protocol.FRAME_SIZE,
        },
    }
    _write_json(destination / "runtime-config.json", runtime_config)
    return destination


def patch_launcher(
    launcher_path: Path,
    *,
    show_runner: Path,
    drone_root: Path,
    bridge_config_root: Path,
) -> Path:
    launcher = _read_json(launcher_path.resolve())
    assets = launcher.get("assets")
    if not isinstance(assets, list):
        raise ShowRuntimeError("Launcher has no assets array")
    by_name = {
        asset.get("name"): asset for asset in assets if isinstance(asset, dict)
    }
    runner = by_name.get("show-runner")
    bridge = by_name.get("web-bridge-fleets")
    if not isinstance(runner, dict) or not isinstance(bridge, dict):
        raise ShowRuntimeError("Launcher is missing show-runner or web-bridge-fleets")
    args = runner.get("args")
    if not isinstance(args, list) or not args:
        raise ShowRuntimeError("show-runner Launcher arguments are invalid")
    args[0] = str(show_runner.resolve())
    if "--wait-for-show-start" not in args:
        args.append("--wait-for-show-start")
    environment = runner.setdefault("env", {}).setdefault("set", {})
    environment["HAKO_DRONE_ROOT"] = str(drone_root.resolve())

    bridge_args = bridge.get("args")
    if not isinstance(bridge_args, list) or "--config-root" not in bridge_args:
        raise ShowRuntimeError("WebBridge Launcher arguments are invalid")
    root_index = bridge_args.index("--config-root") + 1
    bridge_args[root_index] = str(bridge_config_root.resolve())
    _write_json(launcher_path, launcher)
    return launcher_path
