"""Validation helpers for the Drone Show Global Wind JSON protocol."""

from __future__ import annotations

import math
import json
import re
import struct
from collections.abc import Mapping
from typing import Any


SCHEMA = "hakoniwa.drone-show/global-wind/v1"
FRAME_SIZE = 1024
MAGIC = b"HDW1"
HEADER = struct.Struct(">4sHH")
HEADER_SIZE = HEADER.size
MAX_JSON_BYTES = FRAME_SIZE - HEADER_SIZE
ROBOT_NAME = "DroneShow"
COMMAND_PDU_NAME = "global_wind_command"
COMMAND_CHANNEL_ID = 2
MAX_SEQUENCE = (1 << 53) - 1
MAX_ABS_COMPONENT_M_S = 100.0
MAX_SPEED_STDDEV_M_S = 100.0
_PUBLISHER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


class GlobalWindProtocolError(ValueError):
    """Raised when a Global Wind message violates the wire contract."""


def canonical_json(message: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(message), ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def encode_frame(message: Mapping[str, Any]) -> bytes:
    """Encode one validated command into the fixed-size SHM PDU."""

    normalized = validate_message(message)
    payload = canonical_json(normalized)
    if len(payload) > MAX_JSON_BYTES:
        raise GlobalWindProtocolError(
            f"encoded JSON exceeds the {MAX_JSON_BYTES}-byte frame payload limit"
        )
    frame = bytearray(FRAME_SIZE)
    HEADER.pack_into(frame, 0, MAGIC, len(payload), 0)
    frame[HEADER_SIZE : HEADER_SIZE + len(payload)] = payload
    return bytes(frame)


def decode_frame(frame: bytes | bytearray | memoryview) -> dict[str, Any] | None:
    """Decode one fixed-size SHM PDU; an empty slot has no command."""

    raw = bytes(frame)
    if len(raw) != FRAME_SIZE:
        raise GlobalWindProtocolError(
            f"frame must contain exactly {FRAME_SIZE} bytes, got {len(raw)}"
        )
    if not any(raw):
        return None
    magic, payload_size, flags = HEADER.unpack_from(raw)
    if magic != MAGIC:
        raise GlobalWindProtocolError("invalid Global Wind frame magic")
    if flags != 0:
        raise GlobalWindProtocolError(f"unsupported Global Wind frame flags: {flags}")
    if payload_size < 2 or payload_size > MAX_JSON_BYTES:
        raise GlobalWindProtocolError(f"invalid JSON payload size: {payload_size}")
    payload_end = HEADER_SIZE + payload_size
    if any(raw[payload_end:]):
        raise GlobalWindProtocolError("non-zero data follows the declared JSON payload")
    try:
        decoded = json.loads(raw[HEADER_SIZE:payload_end].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GlobalWindProtocolError(f"invalid UTF-8 JSON payload: {exc}") from exc
    return validate_message(decoded)


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GlobalWindProtocolError(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise GlobalWindProtocolError(f"{field} must be a finite number")
    return number


def validate_message(message: Any) -> dict[str, Any]:
    if not isinstance(message, dict):
        raise GlobalWindProtocolError("message must be a JSON object")
    if set(message) != {"schema", "publisher_id", "sequence", "source", "wind"}:
        raise GlobalWindProtocolError("message contains missing or unknown fields")
    if message.get("schema") != SCHEMA:
        raise GlobalWindProtocolError("unsupported Global Wind schema")

    publisher_id = message.get("publisher_id")
    if not isinstance(publisher_id, str) or _PUBLISHER_ID_RE.fullmatch(publisher_id) is None:
        raise GlobalWindProtocolError("invalid publisher_id")

    sequence = message.get("sequence")
    if (
        isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or sequence < 1
        or sequence > MAX_SEQUENCE
    ):
        raise GlobalWindProtocolError("sequence must be a positive safe integer")

    source = message.get("source")
    if not isinstance(source, dict) or set(source) != {"mode", "provider", "observed_at"}:
        raise GlobalWindProtocolError("invalid source")
    if source.get("mode") not in {"manual", "live", "scenario"}:
        raise GlobalWindProtocolError("unsupported source.mode")
    if source.get("provider") is not None and not isinstance(source.get("provider"), str):
        raise GlobalWindProtocolError("source.provider must be null or a string")
    if source.get("observed_at") is not None and not isinstance(source.get("observed_at"), str):
        raise GlobalWindProtocolError("source.observed_at must be null or a string")

    wind = message.get("wind")
    if not isinstance(wind, dict) or set(wind) not in (
        {"enabled", "vector_ros_m_s"},
        {"enabled", "vector_ros_m_s", "variation"},
    ):
        raise GlobalWindProtocolError("invalid wind")
    enabled = wind.get("enabled")
    if not isinstance(enabled, bool):
        raise GlobalWindProtocolError("wind.enabled must be boolean")
    vector = wind.get("vector_ros_m_s")
    if not isinstance(vector, list) or len(vector) != 3:
        raise GlobalWindProtocolError("wind.vector_ros_m_s must contain three values")
    normalized_vector = []
    for index, value in enumerate(vector):
        number = _finite_number(value, f"wind.vector_ros_m_s[{index}]")
        if abs(number) > MAX_ABS_COMPONENT_M_S:
            raise GlobalWindProtocolError(
                f"wind.vector_ros_m_s[{index}] exceeds {MAX_ABS_COMPONENT_M_S} m/s"
            )
        normalized_vector.append(0.0 if number == 0.0 else number)
    if not enabled and any(normalized_vector):
        raise GlobalWindProtocolError("disabled wind must use a zero vector")

    variation = wind.get("variation", {"speed_stddev_m_s": 0.0, "seed": 1})
    if not isinstance(variation, dict) or set(variation) != {
        "speed_stddev_m_s",
        "seed",
    }:
        raise GlobalWindProtocolError("invalid wind.variation")
    speed_stddev_m_s = _finite_number(
        variation.get("speed_stddev_m_s"), "wind.variation.speed_stddev_m_s"
    )
    if not 0.0 <= speed_stddev_m_s <= MAX_SPEED_STDDEV_M_S:
        raise GlobalWindProtocolError(
            f"wind.variation.speed_stddev_m_s must be within [0, {MAX_SPEED_STDDEV_M_S}]"
        )
    seed = variation.get("seed")
    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or seed < 0
        or seed > MAX_SEQUENCE
    ):
        raise GlobalWindProtocolError(
            "wind.variation.seed must be a non-negative safe integer"
        )

    return {
        "schema": SCHEMA,
        "publisher_id": publisher_id,
        "sequence": sequence,
        "source": dict(source),
        "wind": {
            "enabled": enabled,
            "vector_ros_m_s": normalized_vector,
            "variation": {
                "speed_stddev_m_s": speed_stddev_m_s,
                "seed": seed,
            },
        },
    }


def physical_state_key(message: Mapping[str, Any]) -> tuple[Any, ...]:
    wind = message["wind"]
    if not wind["enabled"]:
        return False, (0.0, 0.0, 0.0)
    variation = wind["variation"]
    return (
        True,
        tuple(float(value) for value in wind["vector_ros_m_s"]),
        float(variation["speed_stddev_m_s"]),
        int(variation["seed"]),
    )


class GlobalWindReceiverState:
    """Apply per-publisher ordering and global physical-state deduplication."""

    def __init__(self) -> None:
        self.last_sequence_by_publisher: dict[str, int] = {}
        self.current_message: dict[str, Any] | None = None
        self.current_key: tuple[Any, ...] | None = None

    def accept(self, message: Any) -> tuple[dict[str, Any], bool]:
        normalized = validate_message(message)
        publisher_id = normalized["publisher_id"]
        sequence = normalized["sequence"]
        previous_sequence = self.last_sequence_by_publisher.get(publisher_id, 0)
        if sequence <= previous_sequence:
            raise GlobalWindProtocolError(
                f"stale sequence for publisher {publisher_id}: {sequence} <= {previous_sequence}"
            )
        self.last_sequence_by_publisher[publisher_id] = sequence

        key = physical_state_key(normalized)
        changed = key != self.current_key
        if changed:
            self.current_key = key
            self.current_message = normalized
        return normalized, changed
