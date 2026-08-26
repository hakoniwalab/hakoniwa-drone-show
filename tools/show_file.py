#!/usr/bin/env python3
"""Load the drone-count-independent source definition for a Drone Show."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path, PureWindowsPath
from typing import Any


IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ShowFileError(ValueError):
    """Raised when a Show File violates the v1 contract."""


def _fail(path: str, message: str) -> None:
    raise ShowFileError(f"{path}: {message}")


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


def _positive(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, "must be a number")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        _fail(path, "must be positive and finite")
    return result


def _non_negative(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, "must be a number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        _fail(path, "must be non-negative and finite")
    return result


def _relative_path(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(path, "must be a non-empty relative path")
    candidate = Path(value)
    if candidate.is_absolute() or PureWindowsPath(value).is_absolute():
        _fail(path, "must be relative to the Show File")
    return value


def _led(value: Any, path: str) -> dict[str, Any]:
    state = _object(value, path)
    _keys(state, path, required={"rgb", "brightness"}, optional={"effect"})
    effect = state.get("effect", "steady")
    if effect != "steady":
        _fail(f"{path}.effect", "v1 supports only 'steady'")
    rgb = state["rgb"]
    if not isinstance(rgb, list) or len(rgb) != 3:
        _fail(f"{path}.rgb", "must contain exactly three integers")
    for index, component in enumerate(rgb):
        if (
            isinstance(component, bool)
            or not isinstance(component, int)
            or not 0 <= component <= 255
        ):
            _fail(f"{path}.rgb[{index}]", "must be an integer within [0, 255]")
    brightness = state["brightness"]
    if (
        isinstance(brightness, bool)
        or not isinstance(brightness, (int, float))
        or not math.isfinite(float(brightness))
        or not 0.0 <= float(brightness) <= 1.0
    ):
        _fail(f"{path}.brightness", "must be within [0, 1]")
    return {
        "effect": effect,
        "rgb": list(rgb),
        "brightness": float(brightness),
    }


def validate_show_file(value: Any) -> dict[str, Any]:
    """Validate and normalize a Show File v1 document."""

    root = _object(value, "$")
    _keys(
        root,
        "$",
        required={"schema_version", "show_id", "formations", "timeline"},
        optional={"title", "assignment"},
    )
    if root["schema_version"] != "1.0":
        _fail("$.schema_version", "must be '1.0'")
    show_id = _identifier(root["show_id"], "$.show_id")
    title = root.get("title", show_id)
    if not isinstance(title, str) or not title.strip() or len(title) > 128:
        _fail("$.title", "must be a non-empty string of at most 128 characters")

    assignment = root.get("assignment", {"strategy": "index"})
    assignment = _object(assignment, "$.assignment")
    _keys(assignment, "$.assignment", required={"strategy"})
    if assignment["strategy"] not in {"index", "nearest-greedy"}:
        _fail("$.assignment.strategy", "must be 'index' or 'nearest-greedy'")

    formations = root["formations"]
    if not isinstance(formations, list) or not formations:
        _fail("$.formations", "must be a non-empty array")
    normalized_formations = []
    formation_ids: set[str] = set()
    for index, raw in enumerate(formations):
        path = f"$.formations[{index}]"
        formation = _object(raw, path)
        _keys(formation, path, required={"formation_id", "svg"}, optional={"title"})
        formation_id = _identifier(
            formation["formation_id"], f"{path}.formation_id"
        )
        if formation_id in formation_ids:
            _fail(f"{path}.formation_id", "must be unique")
        formation_ids.add(formation_id)
        formation_title = formation.get("title", formation_id)
        if (
            not isinstance(formation_title, str)
            or not formation_title.strip()
            or len(formation_title) > 128
        ):
            _fail(f"{path}.title", "must be a non-empty string of at most 128 characters")
        normalized_formations.append(
            {
                "formation_id": formation_id,
                "svg": _relative_path(formation["svg"], f"{path}.svg"),
                "title": formation_title,
            }
        )

    timeline = root["timeline"]
    if not isinstance(timeline, list) or not timeline:
        _fail("$.timeline", "must be a non-empty array")
    normalized_timeline = []
    step_ids: set[str] = set()
    for index, raw in enumerate(timeline):
        path = f"$.timeline[{index}]"
        step = _object(raw, path)
        _keys(
            step,
            path,
            required={
                "step_id",
                "formation_id",
                "transition_sec",
                "hold_sec",
                "led",
            },
        )
        step_id = _identifier(step["step_id"], f"{path}.step_id")
        if step_id in step_ids:
            _fail(f"{path}.step_id", "must be unique")
        step_ids.add(step_id)
        formation_id = _identifier(
            step["formation_id"], f"{path}.formation_id"
        )
        if formation_id not in formation_ids:
            _fail(f"{path}.formation_id", "does not reference a Formation")
        normalized_timeline.append(
            {
                "step_id": step_id,
                "formation_id": formation_id,
                "transition_sec": _positive(
                    step["transition_sec"], f"{path}.transition_sec"
                ),
                "hold_sec": _non_negative(step["hold_sec"], f"{path}.hold_sec"),
                "led": _led(step["led"], f"{path}.led"),
            }
        )

    return {
        "schema_version": "1.0",
        "show_id": show_id,
        "title": title,
        "assignment": {"strategy": assignment["strategy"]},
        "formations": normalized_formations,
        "timeline": normalized_timeline,
    }


def load_show_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShowFileError(f"invalid Show File {path}: {exc}") from exc
    return validate_show_file(value)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("path", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        value = load_show_file(args.path.resolve())
    except ShowFileError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(
        f"valid Show File: {value['show_id']} "
        f"({len(value['formations'])} formations, {len(value['timeline'])} steps)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
