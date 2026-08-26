#!/usr/bin/env python3
"""Validate Hakoniwa Show Plan v0.1 artifacts and their Formation references."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path, PureWindowsPath
from typing import Any

from tools.formation import FormationValidationError, validate_formation


IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ShowPlanValidationError(ValueError):
    """Raised when a Show Plan document violates the v0.1 contract."""


def _fail(path: str, message: str) -> None:
    raise ShowPlanValidationError(f"{path}: {message}")


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


def _non_negative(value: Any, path: str) -> float:
    result = _number(value, path)
    if result < 0:
        _fail(path, "must be non-negative")
    return result


def _positive(value: Any, path: str) -> float:
    result = _number(value, path)
    if result <= 0:
        _fail(path, "must be positive")
    return result


def _validate_placement(value: Any) -> None:
    placement = _object(value, "$.placement")
    _keys(
        placement,
        "$.placement",
        required={"latitude_deg", "longitude_deg", "altitude_offset_m", "heading_deg"},
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


def _validate_transform(value: Any, path: str) -> None:
    transform = _object(value, path)
    _keys(
        transform,
        path,
        required={"scale_m", "translation_m", "yaw_deg", "tilt_deg"},
    )
    if _number(transform["scale_m"], f"{path}.scale_m") <= 0:
        _fail(f"{path}.scale_m", "must be positive")
    translation = transform["translation_m"]
    if not isinstance(translation, list) or len(translation) != 3:
        _fail(f"{path}.translation_m", "must contain [east, north, up]")
    for axis, component in zip(("east", "north", "up"), translation):
        _number(component, f"{path}.translation_m.{axis}")
    yaw = _number(transform["yaw_deg"], f"{path}.yaw_deg")
    tilt = _number(transform["tilt_deg"], f"{path}.tilt_deg")
    if not 0 <= yaw < 360:
        _fail(f"{path}.yaw_deg", "must be within [0, 360)")
    if not -90 <= tilt <= 90:
        _fail(f"{path}.tilt_deg", "must be within [-90, 90]")


def _validate_led_state(value: Any, path: str) -> None:
    state = _object(value, path)
    _keys(state, path, required={"effect", "rgb", "brightness"})
    if state["effect"] != "steady":
        _fail(f"{path}.effect", "v0.1 supports only 'steady'")
    rgb = state["rgb"]
    if not isinstance(rgb, list) or len(rgb) != 3:
        _fail(f"{path}.rgb", "must contain exactly three integers")
    for index, component in enumerate(rgb):
        if isinstance(component, bool) or not isinstance(component, int):
            _fail(f"{path}.rgb[{index}]", "must be an integer")
        if not 0 <= component <= 255:
            _fail(f"{path}.rgb[{index}]", "must be within [0, 255]")
    brightness = _number(state["brightness"], f"{path}.brightness")
    if not 0 <= brightness <= 1:
        _fail(f"{path}.brightness", "must be within [0, 1]")


def _validate_led_plan(value: Any, path: str, *, require_default: bool) -> set[str]:
    plan = _object(value, path)
    _keys(
        plan,
        path,
        required={"default"} if require_default else set(),
        optional={"default", "roles"},
    )
    if not plan:
        _fail(path, "must contain default and/or roles")
    if "default" in plan:
        _validate_led_state(plan["default"], f"{path}.default")
    roles = plan.get("roles", [])
    if not isinstance(roles, list) or ("roles" in plan and not roles):
        _fail(f"{path}.roles", "must be a non-empty array when present")
    role_ids: list[str] = []
    for index, raw_override in enumerate(roles):
        role_path = f"{path}.roles[{index}]"
        override = _object(raw_override, role_path)
        _keys(override, role_path, required={"led_role", "state"})
        role_ids.append(_identifier(override["led_role"], f"{role_path}.led_role"))
        _validate_led_state(override["state"], f"{role_path}.state")
    if len(set(role_ids)) != len(role_ids):
        _fail(f"{path}.roles", "must not repeat an led_role")
    return set(role_ids)


def _validate_fleet(value: Any) -> int:
    fleet = _object(value, "$.fleet")
    _keys(fleet, "$.fleet", required={"drone_count", "drone_id_pattern", "assignment"})
    count = fleet["drone_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        _fail("$.fleet.drone_count", "must be a positive integer")
    pattern = _object(fleet["drone_id_pattern"], "$.fleet.drone_id_pattern")
    _keys(pattern, "$.fleet.drone_id_pattern", required={"prefix", "start", "zero_padding"})
    prefix = pattern["prefix"]
    start = pattern["start"]
    padding = pattern["zero_padding"]
    if not isinstance(prefix, str) or len(prefix) > 48:
        _fail("$.fleet.drone_id_pattern.prefix", "must be a string of at most 48 characters")
    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        _fail("$.fleet.drone_id_pattern.start", "must be a non-negative integer")
    if isinstance(padding, bool) or not isinstance(padding, int) or not 0 <= padding <= 12:
        _fail("$.fleet.drone_id_pattern.zero_padding", "must be an integer within [0, 12]")
    for index in range(count):
        number = str(start + index).zfill(padding)
        _identifier(f"{prefix}{number}", f"$.fleet.drone_id_pattern (generated index {index})")
    assignment = _object(fleet["assignment"], "$.fleet.assignment")
    _keys(assignment, "$.fleet.assignment", required={"strategy"})
    if assignment["strategy"] not in {"index", "nearest-greedy"}:
        _fail("$.fleet.assignment.strategy", "must be index or nearest-greedy")
    return count


def _relative_path(value: Any, path: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 512:
        _fail(path, "must be a non-empty path of at most 512 characters")
    if Path(value).is_absolute() or PureWindowsPath(value).is_absolute():
        _fail(path, "must be relative to the Show Plan file")
    if "://" in value:
        _fail(path, "must be a local relative path, not a URI")
    return value


def _load_formation(
    reference: dict[str, Any], reference_path: str, base_directory: Path
) -> dict[str, Any]:
    path = (base_directory / reference["path"]).resolve()
    try:
        payload = path.read_bytes()
    except OSError as exc:
        _fail(f"{reference_path}.path", f"cannot read {path}: {exc}")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != reference["sha256"]:
        _fail(
            f"{reference_path}.sha256",
            f"does not match {path} (actual {digest})",
        )
    try:
        value = json.loads(payload)
        return validate_formation(value)
    except json.JSONDecodeError as exc:
        _fail(f"{reference_path}.path", f"invalid JSON in {path}: {exc}")
    except FormationValidationError as exc:
        _fail(f"{reference_path}.path", f"invalid Formation {path}: {exc}")


def validate_show_plan(
    value: Any, *, base_directory: Path | None = None
) -> dict[str, Any]:
    """Validate and return a Show Plan v0.1 document."""
    root = _object(value, "$")
    _keys(
        root,
        "$",
        required={"schema_version", "show_id", "time_unit", "fleet", "formations", "defaults", "timeline"},
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
    if "placement" in root:
        _validate_placement(root["placement"])
    drone_count = _validate_fleet(root["fleet"])

    references = root["formations"]
    if not isinstance(references, list) or not references:
        _fail("$.formations", "must be a non-empty array")
    formation_ids: list[str] = []
    loaded_formations: dict[str, dict[str, Any]] = {}
    for index, raw_reference in enumerate(references):
        path = f"$.formations[{index}]"
        reference = _object(raw_reference, path)
        _keys(reference, path, required={"formation_id", "path", "sha256"})
        formation_id = _identifier(reference["formation_id"], f"{path}.formation_id")
        formation_ids.append(formation_id)
        _relative_path(reference["path"], f"{path}.path")
        if not isinstance(reference["sha256"], str) or not SHA256.fullmatch(reference["sha256"]):
            _fail(f"{path}.sha256", "must be 64 lowercase hexadecimal characters")
        if base_directory is not None:
            formation = _load_formation(reference, path, base_directory)
            if formation["formation_id"] != formation_id:
                _fail(f"{path}.formation_id", "does not match the referenced Formation")
            if len(formation["points"]) != drone_count:
                _fail(
                    f"{path}.path",
                    f"Formation has {len(formation['points'])} points; fleet requires {drone_count}",
                )
            loaded_formations[formation_id] = formation
    if len(set(formation_ids)) != len(formation_ids):
        _fail("$.formations", "formation_id values must be unique")

    defaults = _object(root["defaults"], "$.defaults")
    _keys(defaults, "$.defaults", required={"transition_sec", "hold_sec", "transform", "led"})
    default_transition = _positive(defaults["transition_sec"], "$.defaults.transition_sec")
    default_hold = _non_negative(defaults["hold_sec"], "$.defaults.hold_sec")
    _validate_transform(defaults["transform"], "$.defaults.transform")
    default_roles = _validate_led_plan(defaults["led"], "$.defaults.led", require_default=True)

    timeline = root["timeline"]
    if not isinstance(timeline, list) or not timeline:
        _fail("$.timeline", "must be a non-empty array")
    step_ids: list[str] = []
    used_formations: set[str] = set()
    for index, raw_step in enumerate(timeline):
        path = f"$.timeline[{index}]"
        step = _object(raw_step, path)
        _keys(
            step,
            path,
            required={"step_id", "formation_id"},
            optional={"transition_sec", "hold_sec", "transform", "led"},
        )
        step_ids.append(_identifier(step["step_id"], f"{path}.step_id"))
        formation_id = _identifier(step["formation_id"], f"{path}.formation_id")
        if formation_id not in formation_ids:
            _fail(f"{path}.formation_id", "must reference an entry in $.formations")
        used_formations.add(formation_id)
        transition = (
            _positive(step["transition_sec"], f"{path}.transition_sec")
            if "transition_sec" in step
            else default_transition
        )
        hold = (
            _non_negative(step["hold_sec"], f"{path}.hold_sec")
            if "hold_sec" in step
            else default_hold
        )
        if "transform" in step:
            _validate_transform(step["transform"], f"{path}.transform")
        step_roles = (
            _validate_led_plan(step["led"], f"{path}.led", require_default=False)
            if "led" in step
            else set()
        )
        if base_directory is not None and step_roles:
            available_roles = {
                point["led_role"] for point in loaded_formations[formation_id]["points"]
            }
            unknown = sorted(step_roles - available_roles)
            if unknown:
                _fail(f"{path}.led.roles", f"roles not present in Formation: {', '.join(unknown)}")
    if len(set(step_ids)) != len(step_ids):
        _fail("$.timeline", "step_id values must be unique")
    if base_directory is not None and default_roles:
        available_roles = {
            point["led_role"]
            for formation_id in used_formations
            for point in loaded_formations[formation_id]["points"]
        }
        unknown = sorted(default_roles - available_roles)
        if unknown:
            _fail("$.defaults.led.roles", f"roles not present in used Formations: {', '.join(unknown)}")
    return root


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ShowPlanValidationError(f"{path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ShowPlanValidationError(
            f"{path}:{exc.lineno}:{exc.colno}: invalid JSON: {exc.msg}"
        ) from exc


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate a Show Plan and its Formation files")
    validate.add_argument("path", type=Path)
    validate.add_argument(
        "--skip-files",
        action="store_true",
        help="validate only the plan document without loading Formation references",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        value = validate_show_plan(
            _load(args.path),
            base_directory=None if args.skip_files else args.path.resolve().parent,
        )
    except ShowPlanValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    duration = sum(
        float(step.get("transition_sec", value["defaults"]["transition_sec"]))
        + float(step.get("hold_sec", value["defaults"]["hold_sec"]))
        for step in value["timeline"]
    )
    print(
        f"VALID: {args.path} "
        f"(drones={value['fleet']['drone_count']}, formations={len(value['formations'])}, "
        f"steps={len(value['timeline'])}, duration_sec={duration})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
