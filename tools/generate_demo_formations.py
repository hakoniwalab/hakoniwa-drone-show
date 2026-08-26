#!/usr/bin/env python3
"""Regenerate the three 128-point demo Formations from their SVG sources."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from tools.svg_to_formation import convert_svg


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "assets" / "formations"
DEFAULT_OUTPUT = ROOT / "examples" / "formations"
DEFAULT_POINT_COUNT = 128


@dataclass(frozen=True)
class DemoFormation:
    base_id: str
    svg_name: str
    title: str


def demo_formations() -> tuple[DemoFormation, ...]:
    return (
        DemoFormation("round-ear-face", "round-ear-face.svg", "Round-ear face"),
        DemoFormation("cat-ear-face", "cat-ear-face.svg", "Cat-ear face"),
        DemoFormation("long-ear-face", "long-ear-face.svg", "Long-ear face"),
    )


def generate_demo(
    specification: DemoFormation,
    *,
    input_directory: Path = DEFAULT_INPUT,
    point_count: int = DEFAULT_POINT_COUNT,
) -> dict:
    path = input_directory / specification.svg_name
    return convert_svg(
        path,
        formation_id=f"{specification.base_id}-{point_count}",
        point_count=point_count,
        title=f"{specification.title} ({point_count} points)",
        source_uri=f"assets/formations/{specification.svg_name}",
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--point-count", type=int, default=DEFAULT_POINT_COUNT)
    return result


def main() -> int:
    args = parser().parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for specification in demo_formations():
        document = generate_demo(
            specification,
            input_directory=args.input,
            point_count=args.point_count,
        )
        path = args.output / f"{document['formation_id']}.json"
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"generated: {path} ({len(document['points'])} points)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
