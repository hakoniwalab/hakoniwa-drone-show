"""Validation and Hakoniwa show-time playback for reproducible wind scenarios."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from tools import global_wind_protocol, show_control_protocol


SCHEMA_VERSION = 1
MAX_TIME_SEC = 24 * 60 * 60
MAX_SPEED_M_S = 100.0
MAX_STDDEV_M_S = 100.0
MAX_SAFE_INTEGER = (1 << 53) - 1
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class WindScenarioError(ValueError):
    pass


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WindScenarioError(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise WindScenarioError(f"{field} must be a finite number")
    return number


def validate_wind_scenario(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WindScenarioError("scenario must be a JSON object")
    required = {"schema_version", "scenario_id", "seed", "events", "vehicle_variation"}
    if set(value) != required:
        raise WindScenarioError("scenario contains missing or unknown fields")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise WindScenarioError("unsupported schema_version")
    scenario_id = value.get("scenario_id")
    if not isinstance(scenario_id, str) or _ID_RE.fullmatch(scenario_id) is None:
        raise WindScenarioError("invalid scenario_id")
    seed = value.get("seed")
    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or not 0 <= seed <= MAX_SAFE_INTEGER
    ):
        raise WindScenarioError("seed must be a non-negative safe integer")
    variation = value.get("vehicle_variation")
    if not isinstance(variation, dict) or set(variation) != {"type", "speed_stddev_m_s"}:
        raise WindScenarioError("invalid vehicle_variation")
    if variation.get("type") != "fixed_gain":
        raise WindScenarioError("vehicle_variation.type must be fixed_gain")
    stddev = _finite(
        variation.get("speed_stddev_m_s"),
        "vehicle_variation.speed_stddev_m_s",
    )
    if not 0.0 <= stddev <= MAX_STDDEV_M_S:
        raise WindScenarioError(
            f"vehicle_variation.speed_stddev_m_s must be within [0, {MAX_STDDEV_M_S}]"
        )

    raw_events = value.get("events")
    if not isinstance(raw_events, list) or not raw_events:
        raise WindScenarioError("events must be a non-empty array")
    events: list[dict[str, Any]] = []
    previous_time = -1.0
    for index, raw in enumerate(raw_events):
        field = f"events[{index}]"
        if not isinstance(raw, dict) or set(raw) != {
            "time_sec", "enabled", "speed_m_s", "direction_to_deg"
        }:
            raise WindScenarioError(f"{field} contains missing or unknown fields")
        time_sec = _finite(raw.get("time_sec"), f"{field}.time_sec")
        if not 0.0 <= time_sec <= MAX_TIME_SEC:
            raise WindScenarioError(f"{field}.time_sec is out of range")
        if time_sec <= previous_time:
            raise WindScenarioError("event times must be strictly increasing")
        if index == 0 and time_sec != 0.0:
            raise WindScenarioError("the first event must start at time_sec=0")
        previous_time = time_sec
        enabled = raw.get("enabled")
        if not isinstance(enabled, bool):
            raise WindScenarioError(f"{field}.enabled must be boolean")
        speed = _finite(raw.get("speed_m_s"), f"{field}.speed_m_s")
        if not 0.0 <= speed <= MAX_SPEED_M_S:
            raise WindScenarioError(f"{field}.speed_m_s is out of range")
        if not enabled and speed != 0.0:
            raise WindScenarioError(f"{field} disabled wind must have zero speed")
        direction = _finite(raw.get("direction_to_deg"), f"{field}.direction_to_deg")
        if not 0.0 <= direction < 360.0:
            raise WindScenarioError(f"{field}.direction_to_deg must be within [0, 360)")
        events.append(
            {
                "time_sec": time_sec,
                "enabled": enabled,
                "speed_m_s": speed,
                "direction_to_deg": direction,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "scenario_id": scenario_id,
        "seed": seed,
        "events": events,
        "vehicle_variation": {
            "type": "fixed_gain",
            "speed_stddev_m_s": stddev,
        },
    }


def load_wind_scenario(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.resolve().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WindScenarioError(f"cannot read wind scenario: {exc}") from exc
    return validate_wind_scenario(value)


def flow_direction_to_ros(direction_to_deg: float, speed_m_s: float) -> list[float]:
    theta = math.radians(direction_to_deg)
    values = [speed_m_s * math.cos(theta), -speed_m_s * math.sin(theta), 0.0]
    return [0.0 if abs(value) < 1e-12 else value for value in values]


class WindScenarioPlayer:
    """Emit scenario commands when Show Status crosses event times."""

    def __init__(self, scenario: dict[str, Any]) -> None:
        self.scenario = validate_wind_scenario(scenario)
        self.run_id: str | None = None
        self.last_status_sequence = 0
        self.last_show_time_usec: int | None = None
        self.next_event_index = 0
        self.command_sequence = 0
        self.reset_generation = 0

    def _reset_timeline(self, run_id: str) -> None:
        self.run_id = run_id
        self.last_status_sequence = 0
        self.last_show_time_usec = None
        self.next_event_index = 0
        self.reset_generation += 1

    def _command(self, event: dict[str, Any]) -> dict[str, Any]:
        self.command_sequence += 1
        enabled = event["enabled"]
        speed = event["speed_m_s"] if enabled else 0.0
        publisher_identity = (
            f"{self.scenario['scenario_id']}:{self.run_id or 'pending'}:"
            f"{self.reset_generation}"
        )
        publisher_digest = hashlib.sha256(
            publisher_identity.encode("utf-8")
        ).hexdigest()[:24]
        return global_wind_protocol.validate_message(
            {
                "schema": global_wind_protocol.SCHEMA,
                "publisher_id": f"scenario:{publisher_digest}",
                "sequence": self.command_sequence,
                "source": {
                    "mode": "scenario",
                    "provider": self.scenario["scenario_id"],
                    "observed_at": None,
                },
                "wind": {
                    "enabled": enabled,
                    "vector_ros_m_s": flow_direction_to_ros(
                        event["direction_to_deg"], speed
                    ),
                    "variation": {
                        "speed_stddev_m_s": self.scenario["vehicle_variation"][
                            "speed_stddev_m_s"
                        ],
                        "seed": self.scenario["seed"],
                    },
                },
            }
        )

    def observe_status(self, message: Any) -> list[dict[str, Any]]:
        status = show_control_protocol.validate_message(message)
        if status["kind"] != "status":
            return []
        run_id = status["run_id"]
        if run_id != self.run_id:
            self._reset_timeline(run_id)
        if status["sequence"] <= self.last_status_sequence:
            return []
        self.last_status_sequence = status["sequence"]
        show_time_usec = status.get("show_time_usec")
        if show_time_usec is None or status["state"] not in {"running", "completed"}:
            return []
        if (
            self.last_show_time_usec is not None
            and show_time_usec < self.last_show_time_usec
        ):
            self.next_event_index = 0
            self.reset_generation += 1
        self.last_show_time_usec = show_time_usec
        commands: list[dict[str, Any]] = []
        show_time_sec = show_time_usec / 1_000_000.0
        events = self.scenario["events"]
        while (
            self.next_event_index < len(events)
            and events[self.next_event_index]["time_sec"] <= show_time_sec
        ):
            commands.append(self._command(events[self.next_event_index]))
            self.next_event_index += 1
        return commands
