#!/usr/bin/env python3
"""Validate Hakoniwa Show IR artifacts without runtime dependencies."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ShowIrValidationError(ValueError):
    """Raised when a Show IR document violates the v0.1 contract."""


def _fail(path: str, message: str) -> None:
    raise ShowIrValidationError(f"{path}: {message}")


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    return value


def _exact_keys(
    value: dict[str, Any],
    path: str,
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required - optional)
    if missing:
        _fail(path, f"missing fields: {', '.join(missing)}")
    if unknown:
        _fail(path, f"unknown fields: {', '.join(unknown)}")


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, "must be a number")
    result = float(value)
    if not math.isfinite(result):
        _fail(path, "must be finite")
    return result


def _identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        _fail(path, "must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    return value


def _validate_placement(value: Any) -> None:
    placement = _object(value, "$.placement")
    _exact_keys(
        placement,
        "$.placement",
        required={
            "latitude_deg",
            "longitude_deg",
            "altitude_offset_m",
            "heading_deg",
        },
    )
    latitude = _number(placement["latitude_deg"], "$.placement.latitude_deg")
    longitude = _number(placement["longitude_deg"], "$.placement.longitude_deg")
    _number(placement["altitude_offset_m"], "$.placement.altitude_offset_m")
    heading = _number(placement["heading_deg"], "$.placement.heading_deg")
    if not -90 <= latitude <= 90:
        _fail("$.placement.latitude_deg", "must be within [-90, 90]")
    if not -180 <= longitude <= 180:
        _fail("$.placement.longitude_deg", "must be within [-180, 180]")
    if not 0 <= heading < 360:
        _fail("$.placement.heading_deg", "must be within [0, 360)")


def _validate_led(value: Any, path: str) -> None:
    led = _object(value, path)
    _exact_keys(led, path, required={"rgb", "brightness"})
    rgb = led["rgb"]
    if not isinstance(rgb, list) or len(rgb) != 3:
        _fail(f"{path}.rgb", "must contain exactly three integers")
    for index, component in enumerate(rgb):
        if isinstance(component, bool) or not isinstance(component, int):
            _fail(f"{path}.rgb[{index}]", "must be an integer")
        if not 0 <= component <= 255:
            _fail(f"{path}.rgb[{index}]", "must be within [0, 255]")
    brightness = _number(led["brightness"], f"{path}.brightness")
    if not 0 <= brightness <= 1:
        _fail(f"{path}.brightness", "must be within [0, 1]")


def validate_show_ir(value: Any) -> dict[str, Any]:
    """Validate and return a Show IR v0.1 document."""

    root = _object(value, "$")
    _exact_keys(
        root,
        "$",
        required={
            "schema_version",
            "show_id",
            "time_unit",
            "coordinate_system",
            "interpolation",
            "drone_ids",
            "timeline",
        },
        optional={"title", "placement"},
    )
    if root["schema_version"] != "0.1":
        _fail("$.schema_version", "must be '0.1'")
    _identifier(root["show_id"], "$.show_id")
    if "title" in root and (
        not isinstance(root["title"], str) or not 1 <= len(root["title"]) <= 128
    ):
        _fail("$.title", "must contain 1..128 characters")
    if root["time_unit"] != "second":
        _fail("$.time_unit", "must be 'second'")

    coordinates = _object(root["coordinate_system"], "$.coordinate_system")
    _exact_keys(
        coordinates,
        "$.coordinate_system",
        required={"frame", "position_unit"},
    )
    if coordinates["frame"] != "ENU":
        _fail("$.coordinate_system.frame", "must be 'ENU'")
    if coordinates["position_unit"] != "meter":
        _fail("$.coordinate_system.position_unit", "must be 'meter'")
    if "placement" in root:
        _validate_placement(root["placement"])

    interpolation = _object(root["interpolation"], "$.interpolation")
    _exact_keys(interpolation, "$.interpolation", required={"position", "led"})
    if interpolation["position"] != "linear":
        _fail("$.interpolation.position", "v0.1 supports only 'linear'")
    if interpolation["led"] != "hold":
        _fail("$.interpolation.led", "v0.1 supports only 'hold'")

    drone_ids = root["drone_ids"]
    if not isinstance(drone_ids, list) or not drone_ids:
        _fail("$.drone_ids", "must be a non-empty array")
    resolved_ids = [
        _identifier(drone_id, f"$.drone_ids[{index}]")
        for index, drone_id in enumerate(drone_ids)
    ]
    if len(set(resolved_ids)) != len(resolved_ids):
        _fail("$.drone_ids", "must not contain duplicates")

    timeline = root["timeline"]
    if not isinstance(timeline, list) or not timeline:
        _fail("$.timeline", "must be a non-empty array")
    previous_time: float | None = None
    for frame_index, raw_frame in enumerate(timeline):
        frame_path = f"$.timeline[{frame_index}]"
        frame = _object(raw_frame, frame_path)
        _exact_keys(frame, frame_path, required={"time_sec", "states"})
        time_sec = _number(frame["time_sec"], f"{frame_path}.time_sec")
        if time_sec < 0:
            _fail(f"{frame_path}.time_sec", "must be non-negative")
        if frame_index == 0 and time_sec != 0:
            _fail(f"{frame_path}.time_sec", "the first frame must start at 0")
        if previous_time is not None and time_sec <= previous_time:
            _fail(f"{frame_path}.time_sec", "frame times must be strictly increasing")
        previous_time = time_sec

        states = frame["states"]
        if not isinstance(states, list) or not states:
            _fail(f"{frame_path}.states", "must be a non-empty array")
        state_ids: list[str] = []
        for state_index, raw_state in enumerate(states):
            state_path = f"{frame_path}.states[{state_index}]"
            state = _object(raw_state, state_path)
            _exact_keys(state, state_path, required={"drone_id", "position_m", "led"})
            state_ids.append(_identifier(state["drone_id"], f"{state_path}.drone_id"))
            position = state["position_m"]
            if not isinstance(position, list) or len(position) != 3:
                _fail(f"{state_path}.position_m", "must contain [east, north, up]")
            for axis, component in zip(("east", "north", "up"), position):
                _number(component, f"{state_path}.position_m.{axis}")
            _validate_led(state["led"], f"{state_path}.led")
        if len(set(state_ids)) != len(state_ids):
            _fail(f"{frame_path}.states", "must not repeat a Drone ID")
        if state_ids != resolved_ids:
            _fail(
                f"{frame_path}.states",
                "Drone IDs and order must exactly match $.drone_ids",
            )
    return root


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ShowIrValidationError(f"{path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ShowIrValidationError(
            f"{path}:{exc.lineno}:{exc.colno}: invalid JSON: {exc.msg}"
        ) from exc


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate one Show IR JSON file")
    validate.add_argument("path", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        value = validate_show_ir(_load(args.path))
    except ShowIrValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    print(
        f"VALID: {args.path} "
        f"(drones={len(value['drone_ids'])}, frames={len(value['timeline'])}, "
        f"duration_sec={value['timeline'][-1]['time_sec']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
