"""Generate a dependency-free SVG QR code for a mobile Viewer URL."""

from __future__ import annotations

from pathlib import Path

from tools.thirdparty.qrcodegen import QrCode


def qr_svg(text: str, *, border: int = 4) -> str:
    if not isinstance(text, str) or not text:
        raise ValueError("QR text must be a non-empty string")
    if border < 0:
        raise ValueError("QR border must be non-negative")
    qr = QrCode.encode_text(text, QrCode.Ecc.MEDIUM)
    size = qr.get_size()
    dimension = size + border * 2
    modules = []
    for y in range(size):
        for x in range(size):
            if qr.get_module(x, y):
                modules.append(f"M{x + border},{y + border}h1v1h-1z")
    path = "".join(modules)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {dimension} {dimension}" '
        'shape-rendering="crispEdges">\n'
        '  <rect width="100%" height="100%" fill="#fff"/>\n'
        f'  <path d="{path}" fill="#000"/>\n'
        '</svg>\n'
    )


def write_viewer_qr(output_path: Path, url: str) -> Path:
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(qr_svg(url), encoding="utf-8")
    return output_path
