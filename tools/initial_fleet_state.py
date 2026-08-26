#!/usr/bin/env python3
"""Validate or generate Hakoniwa Initial Fleet State v0.1 artifacts."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class InitialFleetStateValidationError(ValueError):
    """Raised when an Initial Fleet State violates the v0.1 contract."""


def _fail(path: str, message: str) -> None:
    raise InitialFleetStateValidationError(f"{path}: {message}")


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    return value


def _keys(value: dict[str, Any], path: str, required: set[str]) -> None:
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required)
    if missing:
        _fail(path, f"missing fields: {', '.join(missing)}")
    if unknown:
        _fail(path, f"unknown fields: {', '.join(unknown)}")


def _identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        _fail(path, "must be a valid 1..64 character identifier")
    return value


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, "must be a number")
    result = float(value)
    if not math.isfinite(result):
        _fail(path, "must be finite")
    return result


def _validate_led(value: Any, path: str) -> None:
    led = _object(value, path)
    _keys(led, path, {"rgb", "brightness"})
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


def validate_initial_fleet_state(value: Any) -> dict[str, Any]:
    """Validate and return an Initial Fleet State v0.1 document."""
    root = _object(value, "$")
    _keys(root, "$", {"schema_version", "coordinate_system", "states"})
    if root["schema_version"] != "0.1":
        _fail("$.schema_version", "must be '0.1'")
    coordinates = _object(root["coordinate_system"], "$.coordinate_system")
    _keys(coordinates, "$.coordinate_system", {"frame", "position_unit"})
    if coordinates["frame"] != "ENU":
        _fail("$.coordinate_system.frame", "must be 'ENU'")
    if coordinates["position_unit"] != "meter":
        _fail("$.coordinate_system.position_unit", "must be 'meter'")
    states = root["states"]
    if not isinstance(states, list) or not states:
        _fail("$.states", "must be a non-empty array")
    drone_ids: list[str] = []
    for index, raw_state in enumerate(states):
        path = f"$.states[{index}]"
        state = _object(raw_state, path)
        _keys(state, path, {"drone_id", "position_m", "led"})
        drone_ids.append(_identifier(state["drone_id"], f"{path}.drone_id"))
        position = state["position_m"]
        if not isinstance(position, list) or len(position) != 3:
            _fail(f"{path}.position_m", "must contain [east, north, up]")
        for axis, component in zip(("east", "north", "up"), position):
            _number(component, f"{path}.position_m.{axis}")
        _validate_led(state["led"], f"{path}.led")
    if len(set(drone_ids)) != len(drone_ids):
        _fail("$.states", "must not repeat a Drone ID")
    return root


def generate_grid(
    *,
    drone_count: int,
    prefix: str,
    start: int,
    zero_padding: int,
    spacing_m: float,
    altitude_m: float,
    columns: int | None = None,
) -> dict[str, Any]:
    """Generate a centered row-major ENU grid for offline compiler tests."""
    if drone_count < 1:
        raise InitialFleetStateValidationError("--drone-count must be positive")
    if not isinstance(prefix, str) or len(prefix) > 48:
        raise InitialFleetStateValidationError("--prefix must contain at most 48 characters")
    if start < 0:
        raise InitialFleetStateValidationError("--start must be non-negative")
    if not 0 <= zero_padding <= 12:
        raise InitialFleetStateValidationError("--zero-padding must be within [0, 12]")
    if spacing_m <= 0 or not math.isfinite(spacing_m):
        raise InitialFleetStateValidationError("--spacing-m must be positive and finite")
    if not math.isfinite(altitude_m):
        raise InitialFleetStateValidationError("--altitude-m must be finite")
    resolved_columns = columns or math.ceil(math.sqrt(drone_count))
    if resolved_columns < 1:
        raise InitialFleetStateValidationError("--columns must be positive")
    rows = math.ceil(drone_count / resolved_columns)
    states = []
    for index in range(drone_count):
        row, column = divmod(index, resolved_columns)
        east = (column - (resolved_columns - 1) / 2) * spacing_m
        north = ((rows - 1) / 2 - row) * spacing_m
        number = str(start + index).zfill(zero_padding)
        states.append(
            {
                "drone_id": f"{prefix}{number}",
                "position_m": [round(east, 12), round(north, 12), altitude_m],
                "led": {"rgb": [255, 255, 255], "brightness": 1.0},
            }
        )
    document = {
        "schema_version": "0.1",
        "coordinate_system": {"frame": "ENU", "position_unit": "meter"},
        "states": states,
    }
    return validate_initial_fleet_state(document)


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InitialFleetStateValidationError(f"{path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InitialFleetStateValidationError(
            f"{path}:{exc.lineno}:{exc.colno}: invalid JSON: {exc.msg}"
        ) from exc


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate an Initial Fleet State")
    validate.add_argument("path", type=Path)
    generate = commands.add_parser("generate-grid", help="generate an offline centered grid")
    generate.add_argument("--drone-count", type=int, required=True)
    generate.add_argument("--prefix", default="Drone-")
    generate.add_argument("--start", type=int, default=1)
    generate.add_argument("--zero-padding", type=int, default=0)
    generate.add_argument("--spacing-m", type=float, default=1.5)
    generate.add_argument("--altitude-m", type=float, default=0.0)
    generate.add_argument("--columns", type=int)
    generate.add_argument("--output", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "validate":
            value = validate_initial_fleet_state(_load(args.path))
            print(f"VALID: {args.path} (drones={len(value['states'])})")
            return 0
        value = generate_grid(
            drone_count=args.drone_count,
            prefix=args.prefix,
            start=args.start,
            zero_padding=args.zero_padding,
            spacing_m=args.spacing_m,
            altitude_m=args.altitude_m,
            columns=args.columns,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"generated: {args.output} ({len(value['states'])} drones)")
        return 0
    except InitialFleetStateValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
