from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from tools.formation import validate_formation
from tools.generate_demo_formations import demo_formations, generate_demo


ROOT = Path(__file__).resolve().parents[1]


class GenerateDemoFormationsTest(unittest.TestCase):
    def test_committed_examples_match_svg_conversion(self) -> None:
        for specification in demo_formations():
            expected = generate_demo(specification)
            path = ROOT / "examples" / "formations" / f"{expected['formation_id']}.json"
            actual = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(actual, expected, path)

    def test_each_motif_has_128_valid_points(self) -> None:
        for specification in demo_formations():
            document = generate_demo(specification)
            self.assertIs(validate_formation(document), document)
            self.assertEqual(len(document["points"]), 128)
            self.assertEqual(document["source"]["kind"], "svg")

    def test_semantic_groups_are_preserved(self) -> None:
        expected_groups = (
            {"head", "left-ear", "right-ear", "left-eye", "right-eye", "mouth"},
            {"head", "forehead-accent", "left-eye", "right-eye", "mouth"},
            {"head", "left-ear", "right-ear", "left-eye", "right-eye", "mouth"},
        )
        for specification, expected in zip(demo_formations(), expected_groups):
            document = generate_demo(specification)
            counts = Counter(point["group_id"] for point in document["points"])
            self.assertEqual(set(counts), expected)
            self.assertTrue(all(count >= 3 for count in counts.values()))

    def test_generation_is_deterministic(self) -> None:
        for specification in demo_formations():
            self.assertEqual(generate_demo(specification), generate_demo(specification))


if __name__ == "__main__":
    unittest.main()
