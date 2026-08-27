from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.viewer_qr import qr_svg, write_viewer_qr


class ViewerQrTest(unittest.TestCase):
    def test_svg_contains_quiet_zone_and_dark_modules(self) -> None:
        svg = qr_svg("http://192.168.1.23:8000/drone-show/index.html")
        self.assertIn('shape-rendering="crispEdges"', svg)
        self.assertIn('<rect width="100%" height="100%" fill="#fff"/>', svg)
        self.assertIn('<path d="M', svg)

    def test_write_viewer_qr_creates_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "viewer-access" / "viewer-qr.svg"
            self.assertEqual(
                write_viewer_qr(output, "http://192.168.1.23"), output.resolve()
            )
            self.assertTrue(output.is_file())

    def test_empty_text_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty"):
            qr_svg("")


if __name__ == "__main__":
    unittest.main()
