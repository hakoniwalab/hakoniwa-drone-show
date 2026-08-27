#!/usr/bin/env python3
"""Compile a Show Plan, Formations, and initial fleet state into Show IR v0.1."""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path
from typing import Any

from tools.formation import validate_formation
from tools.initial_fleet_state import validate_initial_fleet_state
from tools.show_ir import validate_show_ir
from tools.show_plan import validate_show_plan


class ShowCompileError(ValueError):
    """Raised when valid inputs cannot be resolved into Show IR."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ShowCompileError(f"{path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ShowCompileError(
            f"{path}:{exc.lineno}:{exc.colno}: invalid JSON: {exc.msg}"
        ) from exc


def _drone_ids(plan: dict[str, Any]) -> list[str]:
    fleet = plan["fleet"]
    pattern = fleet["drone_id_pattern"]
    return [
        f"{pattern['prefix']}{str(pattern['start'] + index).zfill(pattern['zero_padding'])}"
        for index in range(fleet["drone_count"])
    ]


def _clean(value: float) -> float:
    rounded = round(value, 12)
    return 0.0 if rounded == 0.0 else rounded


def transform_position(
    position: list[float],
    transform: dict[str, Any],
    *,
    additional_depth_m: float = 0.0,
) -> list[float]:
    """Map Formation [right, up, depth] into local ENU meters."""
    right, up, depth = (float(component) for component in position)
    scale = float(transform["scale_m"])
    east, north, altitude = (float(component) for component in transform["translation_m"])
    yaw = math.radians(float(transform["yaw_deg"]))
    tilt = math.radians(float(transform["tilt_deg"]))
    right_axis = (math.cos(yaw), math.sin(yaw), 0.0)
    depth_axis = (-math.sin(yaw), math.cos(yaw), 0.0)
    vertical_axis = (0.0, 0.0, 1.0)
    tilted_up = tuple(
        math.cos(tilt) * vertical_axis[axis] + math.sin(tilt) * depth_axis[axis]
        for axis in range(3)
    )
    tilted_depth = tuple(
        -math.sin(tilt) * vertical_axis[axis] + math.cos(tilt) * depth_axis[axis]
        for axis in range(3)
    )
    translation = (east, north, altitude)
    return [
        _clean(
            translation[axis]
            + scale
            * (
                right * right_axis[axis]
                + up * tilted_up[axis]
                + depth * tilted_depth[axis]
            )
            + float(additional_depth_m) * tilted_depth[axis]
        )
        for axis in range(3)
    ]


def transform_formation_positions(
    positions: list[list[float]], transform: dict[str, Any]
) -> list[list[float]]:
    """Transform a Formation, optionally curving its center toward the audience."""

    if not positions:
        return []
    depth_m = float(transform.get("depth_m", 0.0))
    rights = [float(position[0]) for position in positions]
    center_right = (min(rights) + max(rights)) / 2.0
    half_width = (max(rights) - min(rights)) / 2.0
    transformed = []
    for position in positions:
        normalized_right = (
            (float(position[0]) - center_right) / half_width
            if half_width > 0.0
            else 0.0
        )
        curve = max(0.0, 1.0 - normalized_right * normalized_right)
        # Negative Formation depth is the audience-facing side. Positive
        # depth_m therefore produces a convex screen without changing its
        # front projection.
        transformed.append(
            transform_position(
                position,
                transform,
                additional_depth_m=-depth_m * curve,
            )
        )
    return transformed


def assign_point_indices(
    current_positions: list[list[float]],
    target_positions: list[list[float]],
    strategy: str,
) -> list[int]:
    """Return the target point index assigned to each Drone in Drone ID order."""
    if len(current_positions) != len(target_positions):
        raise ShowCompileError("current and target position counts must match")
    if strategy == "index":
        return list(range(len(target_positions)))
    if strategy != "nearest-greedy":
        raise ShowCompileError(f"unsupported assignment strategy: {strategy}")
    available = set(range(len(target_positions)))
    assignments = []
    for current in current_positions:
        selected = min(
            available,
            key=lambda index: (
                sum(
                    (float(current[axis]) - float(target_positions[index][axis])) ** 2
                    for axis in range(3)
                ),
                index,
            ),
        )
        assignments.append(selected)
        available.remove(selected)
    return assignments


def _led_map(plan: dict[str, Any], step: dict[str, Any]) -> tuple[dict, dict[str, dict]]:
    default_plan = plan["defaults"]["led"]
    default_state = default_plan["default"]
    roles = {
        override["led_role"]: override["state"]
        for override in default_plan.get("roles", [])
    }
    step_led = step.get("led", {})
    if "default" in step_led:
        default_state = step_led["default"]
    roles.update(
        {
            override["led_role"]: override["state"]
            for override in step_led.get("roles", [])
        }
    )
    return default_state, roles


def _resolved_led(state: dict[str, Any]) -> dict[str, Any]:
    return {"rgb": list(state["rgb"]), "brightness": float(state["brightness"])}


def compile_show(
    plan: dict[str, Any],
    initial_state: dict[str, Any],
    *,
    plan_directory: Path,
) -> dict[str, Any]:
    """Compile validated authoring inputs into a validated Show IR v0.1 document."""
    validate_show_plan(plan, base_directory=plan_directory)
    validate_initial_fleet_state(initial_state)
    drone_ids = _drone_ids(plan)
    initial_ids = [state["drone_id"] for state in initial_state["states"]]
    if initial_ids != drone_ids:
        raise ShowCompileError(
            "Initial Fleet State Drone IDs and order must exactly match the Show Plan fleet"
        )

    formations: dict[str, dict[str, Any]] = {}
    for reference in plan["formations"]:
        path = (plan_directory / reference["path"]).resolve()
        formations[reference["formation_id"]] = validate_formation(_load_json(path))

    current_states = copy.deepcopy(initial_state["states"])
    frames = [{"time_sec": 0.0, "states": copy.deepcopy(current_states)}]
    current_time = 0.0
    strategy = plan["fleet"]["assignment"]["strategy"]
    for step in plan["timeline"]:
        formation = formations[step["formation_id"]]
        transform = step.get("transform", plan["defaults"]["transform"])
        target_positions = transform_formation_positions(
            [point["position"] for point in formation["points"]],
            transform,
        )
        assignments = assign_point_indices(
            [state["position_m"] for state in current_states],
            target_positions,
            strategy,
        )
        default_led_state, role_leds = _led_map(plan, step)
        target_states = []
        for drone_id, point_index in zip(drone_ids, assignments):
            point = formation["points"][point_index]
            led = role_leds.get(point["led_role"], default_led_state)
            target_states.append(
                {
                    "drone_id": drone_id,
                    "position_m": target_positions[point_index],
                    "led": _resolved_led(led),
                }
            )
        transition_sec = float(step.get("transition_sec", plan["defaults"]["transition_sec"]))
        current_time = _clean(current_time + transition_sec)
        frames.append({"time_sec": current_time, "states": copy.deepcopy(target_states)})
        hold_sec = float(step.get("hold_sec", plan["defaults"]["hold_sec"]))
        if hold_sec > 0:
            current_time = _clean(current_time + hold_sec)
            frames.append({"time_sec": current_time, "states": copy.deepcopy(target_states)})
        current_states = target_states

    show_ir = {
        "schema_version": "0.1",
        "show_id": plan["show_id"],
        **({"title": plan["title"]} if "title" in plan else {}),
        "time_unit": "second",
        "coordinate_system": {"frame": "ENU", "position_unit": "meter"},
        **({"placement": copy.deepcopy(plan["placement"])} if "placement" in plan else {}),
        "interpolation": {"position": "linear", "led": "hold"},
        "drone_ids": drone_ids,
        "timeline": frames,
    }
    return validate_show_ir(show_ir)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--plan", type=Path, required=True)
    result.add_argument("--initial-state", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        plan = _load_json(args.plan)
        initial_state = _load_json(args.initial_state)
        show_ir = compile_show(
            plan,
            initial_state,
            plan_directory=args.plan.resolve().parent,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(show_ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (ShowCompileError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        f"generated: {args.output} "
        f"(drones={len(show_ir['drone_ids'])}, frames={len(show_ir['timeline'])}, "
        f"duration_sec={show_ir['timeline'][-1]['time_sec']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
