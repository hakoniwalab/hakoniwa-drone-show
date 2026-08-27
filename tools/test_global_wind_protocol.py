import unittest

from tools.global_wind_protocol import (
    GlobalWindProtocolError,
    GlobalWindReceiverState,
    decode_frame,
    encode_frame,
    validate_message,
)


def command(*, publisher="browser-a", sequence=1, enabled=True, vector=None):
    return {
        "schema": "hakoniwa.drone-show/global-wind/v1",
        "publisher_id": publisher,
        "sequence": sequence,
        "source": {"mode": "manual", "provider": None, "observed_at": None},
        "wind": {
            "enabled": enabled,
            "vector_ros_m_s": [1.0, -2.0, 0.0] if vector is None else vector,
        },
    }


class GlobalWindProtocolTest(unittest.TestCase):
    def test_fixed_frame_round_trip(self):
        frame = encode_frame(command())
        self.assertEqual(len(frame), 1024)
        self.assertEqual(frame[:4], b"HDW1")
        self.assertEqual(decode_frame(frame), validate_message(command()))

    def test_empty_frame_has_no_command(self):
        self.assertIsNone(decode_frame(bytes(1024)))

    def test_frame_rejects_wrong_size_and_padding(self):
        with self.assertRaisesRegex(GlobalWindProtocolError, "exactly 1024"):
            decode_frame(bytes(1023))
        frame = bytearray(encode_frame(command()))
        frame[-1] = 1
        with self.assertRaisesRegex(GlobalWindProtocolError, "non-zero"):
            decode_frame(frame)

    def test_valid_message(self):
        self.assertEqual(validate_message(command())["wind"]["vector_ros_m_s"], [1.0, -2.0, 0.0])

    def test_disabled_requires_zero_vector(self):
        with self.assertRaisesRegex(GlobalWindProtocolError, "zero vector"):
            validate_message(command(enabled=False))
        self.assertFalse(
            validate_message(command(enabled=False, vector=[0, 0, 0]))["wind"]["enabled"]
        )

    def test_rejects_non_finite_and_unknown_fields(self):
        with self.assertRaisesRegex(GlobalWindProtocolError, "finite"):
            validate_message(command(vector=[float("nan"), 0, 0]))
        invalid = command()
        invalid["extra"] = True
        with self.assertRaisesRegex(GlobalWindProtocolError, "unknown"):
            validate_message(invalid)

    def test_change_detection_ignores_same_physical_state(self):
        state = GlobalWindReceiverState()
        _, changed = state.accept(command(sequence=1))
        self.assertTrue(changed)
        _, changed = state.accept(command(sequence=2))
        self.assertFalse(changed)

    def test_sequence_is_scoped_to_publisher(self):
        state = GlobalWindReceiverState()
        state.accept(command(publisher="browser-a", sequence=3))
        with self.assertRaisesRegex(GlobalWindProtocolError, "stale"):
            state.accept(command(publisher="browser-a", sequence=2, vector=[2, 0, 0]))
        _, changed = state.accept(command(publisher="browser-b", sequence=1, vector=[2, 0, 0]))
        self.assertTrue(changed)


if __name__ == "__main__":
    unittest.main()
