from __future__ import annotations

import unittest

from tools import show_control_protocol as protocol


RUN_ID = "1" * 32
SHOW_HASH = "a" * 64


class ShowControlProtocolTest(unittest.TestCase):
    def test_start_command_round_trip_uses_fixed_frame(self) -> None:
        message = protocol.start_command(
            run_id=RUN_ID, show_sha256=SHOW_HASH, sequence=1
        )
        frame = protocol.encode_frame(message)
        self.assertEqual(len(frame), 1024)
        self.assertEqual(frame[:4], b"HDS1")
        self.assertEqual(protocol.decode_frame(frame), message)

    def test_status_round_trip(self) -> None:
        message = protocol.show_status(
            state="waiting",
            run_id=RUN_ID,
            show_sha256=SHOW_HASH,
            sequence=3,
            simulation_time_usec=20000,
        )
        self.assertEqual(protocol.decode_frame(protocol.encode_frame(message)), message)

    def test_never_written_shm_slot_is_empty(self) -> None:
        self.assertIsNone(protocol.decode_frame(bytes(protocol.FRAME_SIZE)))

    def test_truncated_and_trailing_frames_are_rejected(self) -> None:
        message = protocol.start_command(
            run_id=RUN_ID, show_sha256=SHOW_HASH, sequence=1
        )
        frame = protocol.encode_frame(message)
        with self.assertRaisesRegex(protocol.ProtocolError, "exactly 1024"):
            protocol.decode_frame(frame[:-1])
        damaged = bytearray(frame)
        damaged[-1] = 1
        with self.assertRaisesRegex(protocol.ProtocolError, "Non-zero|non-zero"):
            protocol.decode_frame(damaged)

    def test_payload_limit_is_enforced(self) -> None:
        status = protocol.show_status(
            state="failed",
            run_id=RUN_ID,
            show_sha256=SHOW_HASH,
            sequence=1,
            simulation_time_usec=0,
            error="x" * 256,
        )
        self.assertEqual(len(protocol.encode_frame(status)), protocol.FRAME_SIZE)

    def test_start_gate_rejects_stale_or_duplicate_commands(self) -> None:
        gate = protocol.StartGate(run_id=RUN_ID, show_sha256=SHOW_HASH)
        wrong_run = protocol.start_command(
            run_id="2" * 32, show_sha256=SHOW_HASH, sequence=1
        )
        command = protocol.start_command(
            run_id=RUN_ID, show_sha256=SHOW_HASH, sequence=1
        )
        self.assertFalse(gate.accept(wrong_run))
        self.assertTrue(gate.accept(command))
        self.assertFalse(gate.accept(command))


if __name__ == "__main__":
    unittest.main()
