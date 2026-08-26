#!/usr/bin/env python3
"""Convert SVG outlines into a deterministic Hakoniwa Formation JSON file."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from tools.formation import validate_formation


NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
PATH_TOKEN = re.compile(rf"[A-Za-z]|{NUMBER}")
TRANSFORM = re.compile(r"([A-Za-z]+)\s*\(([^)]*)\)")
POINT_PAIR = re.compile(rf"({NUMBER})[\s,]+({NUMBER})")
SUPPORTED_PATH_COMMANDS = frozenset("MmLlHhVvCcSsQqTtZz")
CURVE_SEGMENTS = 24


class SvgConversionError(ValueError):
    """Raised when an SVG cannot be converted deterministically."""


@dataclass(frozen=True)
class Matrix:
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    def __matmul__(self, other: "Matrix") -> "Matrix":
        return Matrix(
            self.a * other.a + self.c * other.b,
            self.b * other.a + self.d * other.b,
            self.a * other.c + self.c * other.d,
            self.b * other.c + self.d * other.d,
            self.a * other.e + self.c * other.f + self.e,
            self.b * other.e + self.d * other.f + self.f,
        )

    def apply(self, point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        return self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f


@dataclass(frozen=True)
class Outline:
    group_id: str
    led_role: str
    points: tuple[tuple[float, float], ...]
    closed: bool
    weight: float


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _numbers(value: str) -> list[float]:
    return [float(item) for item in re.findall(NUMBER, value)]


def _parse_transform(value: str | None) -> Matrix:
    if not value:
        return Matrix()
    result = Matrix()
    position = 0
    for match in TRANSFORM.finditer(value):
        if value[position : match.start()].strip(" ,\t\r\n"):
            raise SvgConversionError(f"invalid transform syntax: {value!r}")
        name = match.group(1)
        values = _numbers(match.group(2))
        if name == "matrix" and len(values) == 6:
            operation = Matrix(*values)
        elif name == "translate" and len(values) in {1, 2}:
            operation = Matrix(e=values[0], f=values[1] if len(values) == 2 else 0.0)
        elif name == "scale" and len(values) in {1, 2}:
            operation = Matrix(a=values[0], d=values[1] if len(values) == 2 else values[0])
        elif name == "rotate" and len(values) in {1, 3}:
            radians = math.radians(values[0])
            rotation = Matrix(
                a=math.cos(radians),
                b=math.sin(radians),
                c=-math.sin(radians),
                d=math.cos(radians),
            )
            if len(values) == 3:
                cx, cy = values[1:]
                operation = Matrix(e=cx, f=cy) @ rotation @ Matrix(e=-cx, f=-cy)
            else:
                operation = rotation
        elif name == "skewX" and len(values) == 1:
            operation = Matrix(c=math.tan(math.radians(values[0])))
        elif name == "skewY" and len(values) == 1:
            operation = Matrix(b=math.tan(math.radians(values[0])))
        else:
            raise SvgConversionError(f"unsupported or invalid transform: {match.group(0)}")
        result = result @ operation
        position = match.end()
    if value[position:].strip(" ,\t\r\n") or position == 0:
        raise SvgConversionError(f"invalid transform syntax: {value!r}")
    return result


def _float(element: ET.Element, name: str, default: float | None = None) -> float:
    raw = element.get(name)
    if raw is None:
        if default is None:
            raise SvgConversionError(f"<{_local_name(element.tag)}> requires {name}")
        return default
    match = re.fullmatch(rf"\s*({NUMBER})(?:px)?\s*", raw)
    if not match:
        raise SvgConversionError(f"{name} must be a unitless or px number, got {raw!r}")
    return float(match.group(1))


def _ellipse_points(cx: float, cy: float, rx: float, ry: float) -> list[tuple[float, float]]:
    if rx <= 0 or ry <= 0:
        raise SvgConversionError("circle/ellipse radii must be positive")
    return [
        (
            cx + rx * math.cos(math.tau * index / 180),
            cy + ry * math.sin(math.tau * index / 180),
        )
        for index in range(180)
    ]


def _rect_points(element: ET.Element) -> list[tuple[float, float]]:
    x = _float(element, "x", 0.0)
    y = _float(element, "y", 0.0)
    width = _float(element, "width")
    height = _float(element, "height")
    if width <= 0 or height <= 0:
        raise SvgConversionError("rect width and height must be positive")
    rx = _float(element, "rx", 0.0)
    ry = _float(element, "ry", 0.0)
    if rx == 0 and ry != 0:
        rx = ry
    if ry == 0 and rx != 0:
        ry = rx
    rx = min(rx, width / 2)
    ry = min(ry, height / 2)
    if rx == 0 and ry == 0:
        return [(x, y), (x + width, y), (x + width, y + height), (x, y + height)]
    points: list[tuple[float, float]] = []
    centers = (
        (x + width - rx, y + ry, -math.pi / 2, 0.0),
        (x + width - rx, y + height - ry, 0.0, math.pi / 2),
        (x + rx, y + height - ry, math.pi / 2, math.pi),
        (x + rx, y + ry, math.pi, 3 * math.pi / 2),
    )
    for cx, cy, start, end in centers:
        points.extend(
            (
                cx + rx * math.cos(start + (end - start) * index / 8),
                cy + ry * math.sin(start + (end - start) * index / 8),
            )
            for index in range(8)
        )
    return points


def _path_tokens(value: str) -> list[str]:
    tokens = PATH_TOKEN.findall(value.replace(",", " "))
    remainder = PATH_TOKEN.sub("", value.replace(",", " "))
    if remainder.strip():
        raise SvgConversionError(f"invalid path data near {remainder.strip()!r}")
    for token in tokens:
        if token.isalpha() and token not in SUPPORTED_PATH_COMMANDS:
            raise SvgConversionError(f"unsupported SVG path command: {token}")
    return tokens


def _curve_point(
    start: tuple[float, float],
    controls: tuple[tuple[float, float], ...],
    end: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    if len(controls) == 1:
        control = controls[0]
        u = 1 - t
        return (
            u * u * start[0] + 2 * u * t * control[0] + t * t * end[0],
            u * u * start[1] + 2 * u * t * control[1] + t * t * end[1],
        )
    c1, c2 = controls
    u = 1 - t
    return (
        u**3 * start[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * end[0],
        u**3 * start[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * end[1],
    )


def _path_outlines(value: str) -> list[tuple[list[tuple[float, float]], bool]]:
    tokens = _path_tokens(value)
    outlines: list[tuple[list[tuple[float, float]], bool]] = []
    points: list[tuple[float, float]] = []
    index = 0
    command = ""
    current = (0.0, 0.0)
    subpath_start = current
    last_control: tuple[float, float] | None = None
    previous_command = ""

    def available(count: int) -> bool:
        return index + count <= len(tokens) and not any(
            token.isalpha() for token in tokens[index : index + count]
        )

    def coordinate(x: float, y: float, relative: bool) -> tuple[float, float]:
        return (current[0] + x, current[1] + y) if relative else (x, y)

    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
        elif not command:
            raise SvgConversionError("path data must begin with a command")
        relative = command.islower()
        upper = command.upper()

        if upper == "Z":
            if points:
                outlines.append((points, True))
                points = []
            current = subpath_start
            last_control = None
            previous_command = command
            command = ""
            continue
        parameter_count = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2}[upper]
        if not available(parameter_count):
            raise SvgConversionError(f"path command {command} has incomplete parameters")
        values = [float(token) for token in tokens[index : index + parameter_count]]
        index += parameter_count

        if upper == "M":
            if points:
                outlines.append((points, False))
            current = coordinate(values[0], values[1], relative)
            subpath_start = current
            points = [current]
            command = "l" if relative else "L"
            last_control = None
        elif upper == "L":
            current = coordinate(values[0], values[1], relative)
            points.append(current)
            last_control = None
        elif upper == "H":
            current = (current[0] + values[0], current[1]) if relative else (values[0], current[1])
            points.append(current)
            last_control = None
        elif upper == "V":
            current = (current[0], current[1] + values[0]) if relative else (current[0], values[0])
            points.append(current)
            last_control = None
        elif upper in {"C", "S", "Q", "T"}:
            start = current
            if upper == "C":
                c1 = coordinate(values[0], values[1], relative)
                c2 = coordinate(values[2], values[3], relative)
                end = coordinate(values[4], values[5], relative)
                controls = (c1, c2)
                last_control = c2
            elif upper == "S":
                c1 = (
                    (2 * current[0] - last_control[0], 2 * current[1] - last_control[1])
                    if previous_command.upper() in {"C", "S"} and last_control
                    else current
                )
                c2 = coordinate(values[0], values[1], relative)
                end = coordinate(values[2], values[3], relative)
                controls = (c1, c2)
                last_control = c2
            elif upper == "Q":
                control = coordinate(values[0], values[1], relative)
                end = coordinate(values[2], values[3], relative)
                controls = (control,)
                last_control = control
            else:
                control = (
                    (2 * current[0] - last_control[0], 2 * current[1] - last_control[1])
                    if previous_command.upper() in {"Q", "T"} and last_control
                    else current
                )
                end = coordinate(values[0], values[1], relative)
                controls = (control,)
                last_control = control
            points.extend(
                _curve_point(start, controls, end, segment / CURVE_SEGMENTS)
                for segment in range(1, CURVE_SEGMENTS + 1)
            )
            current = end
        previous_command = command
    if points:
        outlines.append((points, False))
    return outlines


def _shape_outlines(element: ET.Element) -> list[tuple[list[tuple[float, float]], bool]]:
    name = _local_name(element.tag)
    if name == "use":
        raise SvgConversionError("unsupported SVG element: <use>; expand referenced geometry first")
    if name == "circle":
        radius = _float(element, "r")
        return [(_ellipse_points(_float(element, "cx", 0.0), _float(element, "cy", 0.0), radius, radius), True)]
    if name == "ellipse":
        return [(
            _ellipse_points(
                _float(element, "cx", 0.0),
                _float(element, "cy", 0.0),
                _float(element, "rx"),
                _float(element, "ry"),
            ),
            True,
        )]
    if name == "rect":
        return [(_rect_points(element), True)]
    if name == "line":
        return [(
            [
                (_float(element, "x1", 0.0), _float(element, "y1", 0.0)),
                (_float(element, "x2", 0.0), _float(element, "y2", 0.0)),
            ],
            False,
        )]
    if name in {"polyline", "polygon"}:
        points = [(float(x), float(y)) for x, y in POINT_PAIR.findall(element.get("points", ""))]
        if len(points) < 2:
            raise SvgConversionError(f"<{name}> requires at least two points")
        return [(points, name == "polygon")]
    if name == "path":
        return _path_outlines(element.get("d", ""))
    return []


def _length(points: tuple[tuple[float, float], ...], closed: bool) -> float:
    pairs = list(zip(points, points[1:]))
    if closed:
        pairs.append((points[-1], points[0]))
    return sum(math.hypot(end[0] - start[0], end[1] - start[1]) for start, end in pairs)


def _collect_outlines(root: ET.Element) -> list[Outline]:
    collected: list[Outline] = []
    shape_number = 0

    def visit(
        element: ET.Element,
        parent_matrix: Matrix,
        inherited_group: str | None,
        inherited_role: str | None,
        hidden: bool,
    ) -> None:
        nonlocal shape_number
        name = _local_name(element.tag)
        style = element.get("style", "").replace(" ", "")
        is_hidden = hidden or element.get("display") == "none" or element.get("visibility") == "hidden" or "display:none" in style
        if name in {"defs", "clipPath", "mask", "metadata", "title", "desc"}:
            return
        matrix = parent_matrix @ _parse_transform(element.get("transform"))
        group = element.get("data-group-id") or (element.get("id") if name == "g" else None) or inherited_group
        role = element.get("data-led-role") or inherited_role
        if not is_hidden:
            raw_outlines = _shape_outlines(element)
            if raw_outlines:
                shape_number += 1
                shape_group = element.get("data-group-id") or element.get("id") or group or f"shape-{shape_number:03d}"
                shape_role = element.get("data-led-role") or role or "default"
                explicit_weight = element.get("data-weight")
                transformed_outlines = [
                    (tuple(matrix.apply(point) for point in raw_points), closed)
                    for raw_points, closed in raw_outlines
                ]
                perimeters = [
                    _length(transformed, closed)
                    for transformed, closed in transformed_outlines
                ]
                if any(perimeter <= 0 for perimeter in perimeters):
                    raise SvgConversionError(f"SVG group {shape_group!r} has zero-length geometry")
                total_perimeter = sum(perimeters)
                for (transformed, closed), perimeter in zip(transformed_outlines, perimeters):
                    weight = (
                        float(explicit_weight) * perimeter / total_perimeter
                        if explicit_weight is not None
                        else perimeter
                    )
                    if not math.isfinite(weight) or weight <= 0:
                        raise SvgConversionError(f"SVG group {shape_group!r} has invalid data-weight")
                    collected.append(Outline(shape_group, shape_role, transformed, closed, weight))
        for child in element:
            visit(child, matrix, group, role, is_hidden)

    visit(root, Matrix(), None, None, False)
    if not collected:
        raise SvgConversionError("SVG contains no supported visible geometry")
    return collected


def _allocate(outlines: list[Outline], count: int) -> list[int]:
    minimum = 3
    if count < len(outlines) * minimum:
        raise SvgConversionError(
            f"{count} points cannot cover {len(outlines)} outlines with at least {minimum} each"
        )
    total = sum(outline.weight for outline in outlines)
    ideal = [count * outline.weight / total for outline in outlines]
    allocations = [max(minimum, int(value)) for value in ideal]
    while sum(allocations) < count:
        index = max(range(len(outlines)), key=lambda item: ideal[item] - allocations[item])
        allocations[index] += 1
    while sum(allocations) > count:
        candidates = [item for item, allocation in enumerate(allocations) if allocation > minimum]
        if not candidates:
            raise SvgConversionError("cannot satisfy point allocation")
        index = max(candidates, key=lambda item: allocations[item] - ideal[item])
        allocations[index] -= 1
    return allocations


def _sample(outline: Outline, count: int) -> list[tuple[float, float]]:
    segments = list(zip(outline.points, outline.points[1:]))
    if outline.closed:
        segments.append((outline.points[-1], outline.points[0]))
    lengths = [math.hypot(end[0] - start[0], end[1] - start[1]) for start, end in segments]
    perimeter = sum(lengths)
    denominator = count if outline.closed else max(1, count - 1)
    samples: list[tuple[float, float]] = []
    segment_index = 0
    traversed = 0.0
    for point_index in range(count):
        distance = perimeter * point_index / denominator
        while segment_index + 1 < len(segments) and traversed + lengths[segment_index] < distance:
            traversed += lengths[segment_index]
            segment_index += 1
        start, end = segments[segment_index]
        length = lengths[segment_index]
        ratio = min(1.0, max(0.0, (distance - traversed) / length))
        samples.append((start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio))
    return samples


def _clean(value: float) -> float:
    rounded = round(value, 12)
    return 0.0 if rounded == 0.0 else rounded


def _formation_points(outlines: list[Outline], count: int) -> list[dict]:
    sampled: list[tuple[Outline, float, float]] = []
    for outline, allocation in zip(outlines, _allocate(outlines, count)):
        sampled.extend((outline, x, -y) for x, y in _sample(outline, allocation))
    min_x = min(item[1] for item in sampled)
    max_x = max(item[1] for item in sampled)
    min_y = min(item[2] for item in sampled)
    max_y = max(item[2] for item in sampled)
    extent = max(max_x - min_x, max_y - min_y)
    if extent <= 0:
        raise SvgConversionError("sampled SVG has zero extent")
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    group_counts: dict[str, int] = {}
    result = []
    for outline, x, y in sampled:
        group_counts[outline.group_id] = group_counts.get(outline.group_id, 0) + 1
        result.append(
            {
                "point_id": f"{outline.group_id}-{group_counts[outline.group_id]:03d}",
                "group_id": outline.group_id,
                "led_role": outline.led_role,
                "position": [
                    _clean((x - center_x) / extent),
                    _clean((y - center_y) / extent),
                    0.0,
                ],
            }
        )
    return result


def convert_svg(
    svg_path: Path,
    *,
    formation_id: str,
    point_count: int,
    title: str | None = None,
    source_uri: str | None = None,
) -> dict:
    """Convert one SVG file to a validated Formation v0.1 document."""
    try:
        source = svg_path.read_bytes()
        root = ET.fromstring(source)
    except OSError as exc:
        raise SvgConversionError(f"{svg_path}: {exc}") from exc
    except ET.ParseError as exc:
        raise SvgConversionError(f"{svg_path}: invalid SVG XML: {exc}") from exc
    if _local_name(root.tag) != "svg":
        raise SvgConversionError("document root must be <svg>")
    if point_count < 1:
        raise SvgConversionError("point count must be positive")
    document = {
        "schema_version": "0.1",
        "formation_id": formation_id,
        **({"title": title} if title else {}),
        "coordinate_system": {
            "frame": "FORMATION_LOCAL",
            "axes": ["right", "up", "depth"],
            "position_unit": "normalized",
        },
        "source": {
            "kind": "svg",
            "sha256": hashlib.sha256(source).hexdigest(),
            "uri": source_uri or str(svg_path),
        },
        "points": _formation_points(_collect_outlines(root), point_count),
    }
    validate_formation(document)
    return document


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("svg", type=Path)
    result.add_argument("--formation-id", required=True)
    result.add_argument("--points", type=int, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--title")
    result.add_argument("--source-uri")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        document = convert_svg(
            args.svg,
            formation_id=args.formation_id,
            point_count=args.points,
            title=args.title,
            source_uri=args.source_uri,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (SvgConversionError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"generated: {args.output} ({len(document['points'])} points)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
