from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.svg_to_formation import SvgConversionError, convert_svg


class SvgToFormationTest(unittest.TestCase):
    def convert(self, svg: str, points: int = 24) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.svg"
            path.write_text(svg, encoding="utf-8")
            return convert_svg(
                path,
                formation_id="test-formation",
                point_count=points,
                source_uri="input.svg",
            )

    def test_basic_shapes_groups_roles_and_transform(self) -> None:
        document = self.convert(
            """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
              <g id="outline" data-led-role="body" transform="translate(5 10)">
                <rect width="40" height="20" data-weight="2"/>
              </g>
              <circle id="eye" data-led-role="eyes" cx="25" cy="20" r="4" data-weight="1"/>
            </svg>"""
        )
        self.assertEqual(len(document["points"]), 24)
        self.assertEqual({point["group_id"] for point in document["points"]}, {"outline", "eye"})
        self.assertEqual({point["led_role"] for point in document["points"]}, {"body", "eyes"})

    def test_path_lines_and_curves(self) -> None:
        document = self.convert(
            """<svg xmlns="http://www.w3.org/2000/svg">
              <path id="curve" data-led-role="accent"
                    d="M 0 0 L 20 0 Q 30 0 30 10 C 30 20 20 30 10 30 S 0 20 0 10 Z"/>
            </svg>""",
            points=32,
        )
        self.assertEqual(len(document["points"]), 32)
        self.assertTrue(all(point["group_id"] == "curve" for point in document["points"]))

    def test_svg_y_axis_is_inverted(self) -> None:
        document = self.convert(
            """<svg xmlns="http://www.w3.org/2000/svg">
              <line id="vertical" x1="0" y1="0" x2="0" y2="10"/>
            </svg>""",
            points=3,
        )
        self.assertEqual(document["points"][0]["position"][1], 0.5)
        self.assertEqual(document["points"][-1]["position"][1], -0.5)

    def test_unsupported_arc_has_clear_error(self) -> None:
        with self.assertRaisesRegex(SvgConversionError, "unsupported SVG path command: A"):
            self.convert(
                """<svg xmlns="http://www.w3.org/2000/svg">
                  <path d="M 0 0 A 10 10 0 0 0 20 0"/>
                </svg>"""
            )

    def test_use_requires_expanded_geometry(self) -> None:
        with self.assertRaisesRegex(SvgConversionError, "expand referenced geometry"):
            self.convert(
                """<svg xmlns="http://www.w3.org/2000/svg">
                  <use href="#shape"/>
                </svg>"""
            )

    def test_same_svg_is_deterministic(self) -> None:
        svg = """<svg xmlns="http://www.w3.org/2000/svg"><ellipse id="ring" cx="2" cy="3" rx="2" ry="1"/></svg>"""
        self.assertEqual(self.convert(svg), self.convert(svg))

    def test_consecutive_duplicate_points_are_ignored(self) -> None:
        document = self.convert(
            """<svg xmlns="http://www.w3.org/2000/svg">
              <path id="outline" d="M 0 0 L 0 0 L 10 0 L 10 10 L 0 10 L 0 0 Z"/>
            </svg>""",
            points=32,
        )
        self.assertEqual(len(document["points"]), 32)
        self.assertEqual(len({tuple(point["position"]) for point in document["points"]}), 32)

    def test_all_duplicate_points_report_zero_length(self) -> None:
        with self.assertRaisesRegex(SvgConversionError, "zero-length geometry"):
            self.convert(
                """<svg xmlns="http://www.w3.org/2000/svg">
                  <polyline id="invalid" points="1,1 1,1 1,1"/>
                </svg>"""
            )


if __name__ == "__main__":
    unittest.main()
