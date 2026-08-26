"""Binary framing and validation for the Drone Show control PDU.

Hakoniwa shared-memory PDUs are fixed-size slots.  The application payload is
compact UTF-8 JSON, so an explicit header preserves its variable length while
the transport always writes exactly ``FRAME_SIZE`` bytes.
"""

from __future__ import annotations

import json
import re
import struct
from collections.abc import Mapping
from typing import Any


FRAME_SIZE = 1024
MAGIC = b"HDS1"
HEADER = struct.Struct(">4sHH")
HEADER_SIZE = HEADER.size
MAX_JSON_BYTES = FRAME_SIZE - HEADER_SIZE
PROTOCOL = "hakoniwa.drone-show-control"
SCHEMA_VERSION = 1

ROBOT_NAME = "DroneShow"
COMMAND_PDU_NAME = "show_command"
COMMAND_CHANNEL_ID = 0
STATUS_PDU_NAME = "show_status"
STATUS_CHANNEL_ID = 1

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_STATES = frozenset(
    {"initializing", "waiting", "running", "completed", "failed"}
)


class ProtocolError(ValueError):
    """Raised when a control frame or message violates the wire contract."""


def canonical_json(message: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(message),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def encode_frame(message: Mapping[str, Any]) -> bytes:
    """Validate and encode one message into a fixed 1024-byte SHM frame."""

    validated = validate_message(message)
    payload = canonical_json(validated)
    if len(payload) > MAX_JSON_BYTES:
        raise ProtocolError(
            f"encoded JSON exceeds the {MAX_JSON_BYTES}-byte frame payload limit"
        )
    frame = bytearray(FRAME_SIZE)
    HEADER.pack_into(frame, 0, MAGIC, len(payload), 0)
    frame[HEADER_SIZE : HEADER_SIZE + len(payload)] = payload
    return bytes(frame)


def decode_frame(frame: bytes | bytearray | memoryview) -> dict[str, Any] | None:
    """Decode one frame; an all-zero, never-written SHM slot returns ``None``."""

    raw = bytes(frame)
    if len(raw) != FRAME_SIZE:
        raise ProtocolError(
            f"frame must contain exactly {FRAME_SIZE} bytes, got {len(raw)}"
        )
    if not any(raw):
        return None
    magic, payload_size, flags = HEADER.unpack_from(raw)
    if magic != MAGIC:
        raise ProtocolError("invalid Drone Show frame magic")
    if flags != 0:
        raise ProtocolError(f"unsupported Drone Show frame flags: {flags}")
    if payload_size < 2 or payload_size > MAX_JSON_BYTES:
        raise ProtocolError(f"invalid JSON payload size: {payload_size}")
    payload_end = HEADER_SIZE + payload_size
    if any(raw[payload_end:]):
        raise ProtocolError("non-zero data follows the declared JSON payload")
    try:
        decoded = json.loads(raw[HEADER_SIZE:payload_end].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"invalid UTF-8 JSON payload: {exc}") from exc
    return validate_message(decoded)


def _require_common(message: Mapping[str, Any]) -> None:
    if message.get("schema_version") != SCHEMA_VERSION:
        raise ProtocolError("unsupported schema_version")
    if message.get("protocol") != PROTOCOL:
        raise ProtocolError("unsupported protocol")
    run_id = message.get("run_id")
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        raise ProtocolError("run_id must be 32 lowercase hexadecimal characters")
    show_sha256 = message.get("show_sha256")
    if not isinstance(show_sha256, str) or _HASH_RE.fullmatch(show_sha256) is None:
        raise ProtocolError("show_sha256 must be 64 lowercase hexadecimal characters")
    sequence = message.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ProtocolError("sequence must be a positive integer")


def validate_message(message: Any) -> dict[str, Any]:
    if not isinstance(message, dict):
        raise ProtocolError("message must be a JSON object")
    _require_common(message)
    kind = message.get("kind")
    if kind == "command":
        required = {
            "schema_version",
            "protocol",
            "kind",
            "type",
            "run_id",
            "show_sha256",
            "sequence",
        }
        if set(message) != required:
            raise ProtocolError("START command contains missing or unknown fields")
        if message.get("type") != "START":
            raise ProtocolError("unsupported command type")
    elif kind == "status":
        required = {
            "schema_version",
            "protocol",
            "kind",
            "state",
            "run_id",
            "show_sha256",
            "sequence",
            "simulation_time_usec",
        }
        allowed = required | {"error"}
        fields = set(message)
        if not required <= fields or not fields <= allowed:
            raise ProtocolError("status contains missing or unknown fields")
        state = message.get("state")
        if state not in _STATES:
            raise ProtocolError(f"unsupported status state: {state!r}")
        simulation_time = message.get("simulation_time_usec")
        if (
            isinstance(simulation_time, bool)
            or not isinstance(simulation_time, int)
            or simulation_time < 0
        ):
            raise ProtocolError("simulation_time_usec must be a non-negative integer")
        error = message.get("error")
        if state == "failed":
            if not isinstance(error, str) or not error or len(error) > 256:
                raise ProtocolError("failed status requires an error of 1..256 characters")
        elif "error" in message:
            raise ProtocolError("error is valid only for failed status")
    else:
        raise ProtocolError("kind must be command or status")
    return dict(message)


def start_command(
    *, run_id: str, show_sha256: str, sequence: int
) -> dict[str, Any]:
    return validate_message(
        {
            "schema_version": SCHEMA_VERSION,
            "protocol": PROTOCOL,
            "kind": "command",
            "type": "START",
            "run_id": run_id,
            "show_sha256": show_sha256,
            "sequence": sequence,
        }
    )


def show_status(
    *,
    state: str,
    run_id: str,
    show_sha256: str,
    sequence: int,
    simulation_time_usec: int,
    error: str | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "protocol": PROTOCOL,
        "kind": "status",
        "state": state,
        "run_id": run_id,
        "show_sha256": show_sha256,
        "sequence": sequence,
        "simulation_time_usec": simulation_time_usec,
    }
    if error is not None:
        message["error"] = error[:256]
    return validate_message(message)


class StartGate:
    """Idempotently accepts START only for the current waiting run."""

    def __init__(self, *, run_id: str, show_sha256: str) -> None:
        self.run_id = run_id
        self.show_sha256 = show_sha256
        self.last_sequence = 0
        self.started = False

    def accept(self, message: Mapping[str, Any] | None) -> bool:
        if message is None or self.started:
            return False
        try:
            validated = validate_message(dict(message))
        except ProtocolError:
            return False
        if (
            validated["kind"] != "command"
            or validated["type"] != "START"
            or validated["run_id"] != self.run_id
            or validated["show_sha256"] != self.show_sha256
            or validated["sequence"] <= self.last_sequence
        ):
            return False
        self.last_sequence = validated["sequence"]
        self.started = True
        return True
