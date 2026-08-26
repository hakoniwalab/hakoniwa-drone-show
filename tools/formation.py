#!/usr/bin/env python3
"""Validate reusable Hakoniwa Formation JSON artifacts."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
NORMALIZATION_TOLERANCE = 1e-9


class FormationValidationError(ValueError):
    """Raised when a Formation JSON document violates the v0.1 contract."""


def _fail(path: str, message: str) -> None:
    raise FormationValidationError(f"{path}: {message}")


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    return value


def _keys(
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


def _validate_normalized_positions(positions: list[list[float]]) -> None:
    mins = [min(position[axis] for position in positions) for axis in range(3)]
    maxs = [max(position[axis] for position in positions) for axis in range(3)]
    for axis, name in enumerate(("right", "up", "depth")):
        if abs(mins[axis] + maxs[axis]) > NORMALIZATION_TOLERANCE:
            _fail("$.points", f"{name} bounding box must be centered at 0")
        if mins[axis] < -0.5 - NORMALIZATION_TOLERANCE or maxs[axis] > 0.5 + NORMALIZATION_TOLERANCE:
            _fail("$.points", f"{name} coordinates must stay within [-0.5, 0.5]")
    maximum_extent = max(maxs[axis] - mins[axis] for axis in range(3))
    if maximum_extent <= NORMALIZATION_TOLERANCE:
        if any(abs(component) > NORMALIZATION_TOLERANCE for component in positions[0]):
            _fail("$.points", "a degenerate Formation must be located at the origin")
    elif abs(maximum_extent - 1.0) > NORMALIZATION_TOLERANCE:
        _fail("$.points", "maximum bounding-box extent must equal 1")


def validate_formation(value: Any) -> dict[str, Any]:
    """Validate and return a Formation JSON v0.1 document."""

    root = _object(value, "$")
    _keys(
        root,
        "$",
        required={"schema_version", "formation_id", "coordinate_system", "points"},
        optional={"title", "source"},
    )
    if root["schema_version"] != "0.1":
        _fail("$.schema_version", "must be '0.1'")
    _identifier(root["formation_id"], "$.formation_id")
    if "title" in root and (
        not isinstance(root["title"], str) or not 1 <= len(root["title"]) <= 128
    ):
        _fail("$.title", "must contain 1..128 characters")

    coordinates = _object(root["coordinate_system"], "$.coordinate_system")
    _keys(
        coordinates,
        "$.coordinate_system",
        required={"frame", "axes", "position_unit"},
    )
    if coordinates["frame"] != "FORMATION_LOCAL":
        _fail("$.coordinate_system.frame", "must be 'FORMATION_LOCAL'")
    if coordinates["axes"] != ["right", "up", "depth"]:
        _fail("$.coordinate_system.axes", "must be ['right', 'up', 'depth']")
    if coordinates["position_unit"] != "normalized":
        _fail("$.coordinate_system.position_unit", "must be 'normalized'")

    if "source" in root:
        source = _object(root["source"], "$.source")
        _keys(source, "$.source", required={"kind", "sha256"}, optional={"uri"})
        if source["kind"] not in {"svg", "generated", "imported"}:
            _fail("$.source.kind", "must be svg, generated, or imported")
        if not isinstance(source["sha256"], str) or not SHA256.fullmatch(source["sha256"]):
            _fail("$.source.sha256", "must be 64 lowercase hexadecimal characters")
        if "uri" in source and (
            not isinstance(source["uri"], str) or not 1 <= len(source["uri"]) <= 512
        ):
            _fail("$.source.uri", "must contain 1..512 characters")

    points = root["points"]
    if not isinstance(points, list) or not points:
        _fail("$.points", "must be a non-empty array")
    point_ids: list[str] = []
    positions: list[list[float]] = []
    for index, raw_point in enumerate(points):
        path = f"$.points[{index}]"
        point = _object(raw_point, path)
        _keys(
            point,
            path,
            required={"point_id", "group_id", "led_role", "position"},
        )
        point_ids.append(_identifier(point["point_id"], f"{path}.point_id"))
        _identifier(point["group_id"], f"{path}.group_id")
        _identifier(point["led_role"], f"{path}.led_role")
        raw_position = point["position"]
        if not isinstance(raw_position, list) or len(raw_position) != 3:
            _fail(f"{path}.position", "must contain [right, up, depth]")
        positions.append(
            [
                _number(component, f"{path}.position[{axis}]")
                for axis, component in enumerate(raw_position)
            ]
        )
    if len(set(point_ids)) != len(point_ids):
        _fail("$.points", "point_id values must be unique")
    _validate_normalized_positions(positions)
    return root


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FormationValidationError(f"{path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise FormationValidationError(
            f"{path}:{exc.lineno}:{exc.colno}: invalid JSON: {exc.msg}"
        ) from exc


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate one Formation JSON file")
    validate.add_argument("path", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        value = validate_formation(_load(args.path))
    except FormationValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    print(
        f"VALID: {args.path} "
        f"(formation_id={value['formation_id']}, points={len(value['points'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
