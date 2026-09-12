"""Materialize the minimal browser surface for a BodyFrame Fleet recording."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from tools import show_control_protocol as protocol
from tools.recipe import show_runtime


class RecordingRuntimeError(RuntimeError):
    pass


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecordingRuntimeError(f"invalid JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RecordingRuntimeError(f"JSON root must be an object: {path}")
    return value


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def materialize_viewer(
    *,
    show_root: Path,
    viewer_root: Path,
    output_root: Path,
    drone_count: int,
    process_count: int,
    formation: str,
    real_time_sync: bool,
) -> Path:
    """Copy the normal Fleet viewer and overlay only recording controls.

    The copied viewer keeps the BodyFrame Fleet's normal Three.js state path.
    It deliberately does not materialize a MuJoCo world, Show IR, LEDs, wind,
    or City assets.
    """

    show_root = show_root.resolve()
    viewer_root = viewer_root.resolve()
    output_root = output_root.resolve()
    if drone_count < 1:
        raise RecordingRuntimeError("drone_count must be positive")
    if process_count < 1 or drone_count % process_count:
        raise RecordingRuntimeError("drone_count must be evenly divisible by process_count")
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    for name in ("src", "config", "assets", "thirdparty"):
        source = viewer_root / name
        if not source.is_dir():
            raise RecordingRuntimeError(f"Three.js Viewer resource is missing: {source}")
        shutil.copytree(source, output_root / name)

    viewer_config_path = output_root / "config" / "viewer-config-fleets.json"
    viewer_config = _read_json(viewer_config_path)
    pdu_relative = viewer_config.get("pdu", {}).get("pduDefPath")
    if not isinstance(pdu_relative, str):
        raise RecordingRuntimeError("fleet Viewer config has no pduDefPath")
    pdu_path = (viewer_config_path.parent / pdu_relative).resolve()
    visual = _read_json(pdu_path)
    show_types_name = show_runtime.SHOW_PDUTYPES_FILE
    _write_json(output_root / "config" / show_types_name, show_runtime.show_pdutypes())
    visual["paths"] = [
        item for item in visual.get("paths", [])
        if isinstance(item, dict) and item.get("id") != show_runtime.SHOW_PDUTYPES_ID
    ] + [{"id": show_runtime.SHOW_PDUTYPES_ID, "path": show_types_name}]
    visual["robots"] = [
        item for item in visual.get("robots", [])
        if isinstance(item, dict) and item.get("name") != protocol.ROBOT_NAME
    ] + [{"name": protocol.ROBOT_NAME, "pdutypes_id": show_runtime.SHOW_PDUTYPES_ID}]
    combined_name = "pdudef-fleet-recording.json"
    _write_json(output_root / "config" / combined_name, visual)
    viewer_config["pdu"]["pduDefPath"] = f"./{combined_name}"
    fleet = viewer_config.setdefault("stateInput", {}).setdefault("fleets", {})
    fleet.update({"dynamicSpawn": True, "templateDroneIndex": 0, "maxDynamicDrones": drone_count})
    _write_json(viewer_config_path, viewer_config)

    destination = output_root / "recording"
    shutil.copytree(show_root / "web" / "fleet-recording", destination)
    for name in ("show-control-client.mjs", "show-pdu-codec.mjs"):
        shutil.copy2(show_root / "web" / name, destination / name)
    _write_json(
        destination / "runtime-config.json",
        {
            "schema_version": 1,
            "expected_drone_count": drone_count,
            "websocket_url": "ws://127.0.0.1:8765",
            "conditions": {
                "physics": "BodyFrame",
                "drone_count": drone_count,
                "process_count": process_count,
                "drones_per_process": drone_count // process_count,
                "formation": formation,
                "real_time_sync": real_time_sync,
            },
            "control": {
                "robot_name": protocol.ROBOT_NAME,
                "command_pdu_name": protocol.COMMAND_PDU_NAME,
                "status_pdu_name": protocol.STATUS_PDU_NAME,
                "frame_size": protocol.FRAME_SIZE,
            },
        },
    )
    return output_root
