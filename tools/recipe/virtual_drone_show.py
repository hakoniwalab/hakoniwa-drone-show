#!/usr/bin/env python3
"""Operate the private City-backed virtual drone show Recipe.

The generic single-host fleet runtime stays in Hakoniwa Business Pack.  This
operator owns the PRO-only City show extension and materializes it into the
generic Recipe workspace after the base configuration has been generated.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import ipaddress
import json
import math
import os
import platform
import subprocess
import sys
from pathlib import Path


SHOW_ROOT = Path(__file__).absolute().parents[2]
BUSINESS_PACK_ROOT = Path(
    os.environ.get(
        "HAKONIWA_BUSINESS_PACK_ROOT",
        str(SHOW_ROOT.parent / "hakoniwa-business-pack"),
    )
).expanduser().resolve()
DEFAULT_EXPERIMENT = (
    SHOW_ROOT / "recipes" / "experiments" / "virtual-drone-show-city.yaml"
)
for search_path in (
    BUSINESS_PACK_ROOT,
    BUSINESS_PACK_ROOT / "tools" / "recipe",
    BUSINESS_PACK_ROOT / "tools",
):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))
if str(SHOW_ROOT) not in sys.path:
    sys.path.insert(0, str(SHOW_ROOT))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


base = _load_module(
    "business_pack_drone_fleet_single_host",
    BUSINESS_PACK_ROOT / "tools" / "recipe" / "drone_fleet_single_host.py",
)
city = _load_module(
    "hakoniwa_drone_show_mujoco_city",
    Path(__file__).with_name("drone_fleet_mujoco_city.py"),
)
from tools.recipe import show_runtime
from tools.show_file import ShowFileError, load_show_file
from tools.viewer_qr import write_viewer_qr

base.OPERATOR_COMMAND = "python ../hakoniwa-drone-show/tools/recipe/virtual_drone_show.py"
base.MAP_VIEWER_URL_BASE = (
    "http://127.0.0.1:8000/drone-show/index.html"
    "?threejsRoot=/thirdparty/hakoniwa-threejs-drone"
    "&viewerConfigName=viewer-config-fleets.json"
)
_BASE_WRITE_LAUNCHER = base.write_launcher
_BASE_LOAD_SIMPLE_YAML = base.load_simple_yaml
_BASE_MUJOCO_RUNTIME_CHECKS = base._mujoco_city_runtime_checks
_BASE_SCENARIO_COMPATIBILITY = {
    "type": "hakoniwa-word",
    "word": "HAKONIWA",
}
_LEGACY_BASE_FORMATION_SCALE_M = 61.325
_LEGACY_BASE_WORD_DIMENSIONS = {
    "letter_width_m": 10.0,
    "letter_height_m": 20.0,
    "letter_gap_m": 4.5,
}
_INTERNAL_COMPATIBILITY_FIELDS = (
    set(_BASE_SCENARIO_COMPATIBILITY)
    | set(_LEGACY_BASE_WORD_DIMENSIONS)
    | {"speed_m_s", "duration_sec", "hold_sec"}
)
_DEFAULT_VIEWER_HOST = "127.0.0.1"
_CITY_MARKER_NAME = "mujoco-city-fleet.json"
_FLAT_MARKER_NAME = "mujoco-flat-fleet.json"


def _run_openssl(arguments: list[str]) -> None:
    try:
        completed = subprocess.run(
            ["openssl", *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise base.RecipeError(
            "AR HTTPS certificate generation requires openssl"
        ) from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise base.RecipeError(f"openssl failed: {detail}")


def _prepare_ar_tls(recipe_root: Path, host: str) -> dict[str, Path]:
    host = str(ipaddress.IPv4Address(host))
    output = recipe_root / "ar-tls"
    output.mkdir(parents=True, exist_ok=True)
    ca_key = output / "hakoniwa-ar-ca.key"
    ca_certificate = output / "hakoniwa-ar-ca.crt"
    server_key = output / "hakoniwa-ar-server.key"
    server_certificate = output / "hakoniwa-ar-server.crt"
    server_request = output / "hakoniwa-ar-server.csr"
    server_extensions = output / "hakoniwa-ar-server.ext"
    configured_host = output / "server-host.txt"

    if not ca_key.is_file() or not ca_certificate.is_file():
        _run_openssl(
            [
                "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", str(ca_key), "-out", str(ca_certificate),
                "-days", "3650", "-sha256",
                "-subj", "/CN=Hakoniwa Drone Show Local CA",
                "-addext", "basicConstraints=critical,CA:TRUE",
                "-addext", "keyUsage=critical,keyCertSign,cRLSign",
            ]
        )
        ca_key.chmod(0o600)

    certificate_matches = (
        server_key.is_file()
        and server_certificate.is_file()
        and configured_host.is_file()
        and configured_host.read_text(encoding="utf-8").strip() == host
    )
    if not certificate_matches:
        server_extensions.write_text(
            "\n".join(
                [
                    "basicConstraints=critical,CA:FALSE",
                    "keyUsage=critical,digitalSignature,keyEncipherment",
                    "extendedKeyUsage=serverAuth",
                    f"subjectAltName=IP:{host},IP:127.0.0.1,DNS:localhost",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        _run_openssl(
            [
                "req", "-newkey", "rsa:2048", "-nodes",
                "-keyout", str(server_key), "-out", str(server_request),
                "-sha256", "-subj", f"/CN={host}",
            ]
        )
        _run_openssl(
            [
                "x509", "-req", "-in", str(server_request),
                "-CA", str(ca_certificate), "-CAkey", str(ca_key),
                "-CAcreateserial", "-out", str(server_certificate),
                "-days", "825", "-sha256", "-extfile", str(server_extensions),
            ]
        )
        server_key.chmod(0o600)
        configured_host.write_text(host + "\n", encoding="utf-8")
        server_request.unlink(missing_ok=True)
    return {
        "ca_certificate": ca_certificate,
        "server_certificate": server_certificate,
        "server_key": server_key,
    }


def _environment_settings(experiment_path: Path) -> dict:
    raw = _BASE_LOAD_SIMPLE_YAML(experiment_path)
    value = raw.get("environment", {"mode": "plateau"})
    if not isinstance(value, dict):
        raise base.RecipeError("environment must be a mapping")
    unknown = sorted(set(value) - {"mode", "flat"})
    if unknown:
        raise base.RecipeError("environment has unknown fields: " + ", ".join(unknown))
    mode = value.get("mode", "plateau")
    if mode not in {"plateau", "flat"}:
        raise base.RecipeError("environment.mode must be plateau or flat")
    resolved = {"mode": mode}
    flat = value.get("flat")
    if mode == "flat" and not isinstance(flat, dict):
        raise base.RecipeError("environment.flat is required in flat mode")
    if flat is None:
        return resolved
    if not isinstance(flat, dict):
        raise base.RecipeError("environment.flat must be a mapping")
    unknown_flat = sorted(set(flat) - {"ground_height_m", "origin"})
    if unknown_flat:
        raise base.RecipeError(
            "environment.flat has unknown fields: " + ", ".join(unknown_flat)
        )
    ground_height = flat.get("ground_height_m")
    if (
        not isinstance(ground_height, (int, float))
        or isinstance(ground_height, bool)
        or not math.isfinite(float(ground_height))
    ):
        raise base.RecipeError("environment.flat.ground_height_m must be finite")
    origin = flat.get("origin")
    if not isinstance(origin, dict):
        raise base.RecipeError("environment.flat.origin must be a mapping")
    unknown_origin = sorted(
        set(origin) - {"latitude", "longitude", "altitude_offset_m"}
    )
    if unknown_origin:
        raise base.RecipeError(
            "environment.flat.origin has unknown fields: "
            + ", ".join(unknown_origin)
        )
    coordinates = {}
    for key in ("latitude", "longitude", "altitude_offset_m"):
        item = origin.get(key)
        if (
            not isinstance(item, (int, float))
            or isinstance(item, bool)
            or not math.isfinite(float(item))
        ):
            raise base.RecipeError(f"environment.flat.origin.{key} must be finite")
        coordinates[key] = float(item)
    if not -90.0 <= coordinates["latitude"] <= 90.0:
        raise base.RecipeError("environment.flat.origin.latitude is out of range")
    if not -180.0 <= coordinates["longitude"] <= 180.0:
        raise base.RecipeError("environment.flat.origin.longitude is out of range")
    resolved["flat"] = {
        "ground_height_m": float(ground_height),
        "origin": coordinates,
    }
    return resolved


def _runtime_marker_path(paths) -> Path:
    flat = paths.recipe_config / _FLAT_MARKER_NAME
    if flat.is_file():
        return flat
    return paths.recipe_config / _CITY_MARKER_NAME


def _show_mujoco_runtime_checks(paths, drone_root, experiment, system_name):
    marker_path = paths.recipe_config / _FLAT_MARKER_NAME
    if not marker_path.is_file():
        return _BASE_MUJOCO_RUNTIME_CHECKS(
            paths, drone_root, experiment, system_name
        )
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [("MuJoCo Flat fleet contract", False, str(exc))]
    checks = []
    configured_root = Path(str(marker.get("drone_root", ""))).resolve()
    checks.append(
        (
            "MuJoCo Flat Drone PRO workspace",
            configured_root == drone_root.resolve(),
            f"configured={configured_root}, selected={drone_root.resolve()}",
        )
    )
    checks.append(
        (
            "MuJoCo Flat process-model contract",
            marker.get("process_count") == experiment.process_count,
            f"configured={experiment.process_count}, model={marker.get('process_count')}",
        )
    )
    checks.append(
        (
            "MuJoCo Flat fleet size",
            marker.get("drone_count") == experiment.drone_count,
            f"configured={experiment.drone_count}, model={marker.get('drone_count')}",
        )
    )
    plan = marker.get("flight_plan", {})
    environment = marker.get("environment", {})
    try:
        ground = float(environment["ground_height_m"])
        resolved = float(plan["resolved_flight_altitude_m"])
        points = plan["spawn_points"]
        safety_ok = (
            environment.get("mode") == "flat"
            and len(points) == experiment.drone_count
            and abs(resolved - (ground + experiment.altitude_m)) < 1e-6
            and all(
                abs(float(point["body_origin_height_m"]) - (
                    ground + float(plan["spawn_body_clearance_m"])
                )) < 1e-6
                for point in points
            )
        )
        safety_detail = (
            f"ground={ground:.3f} m, launch_points={len(points)}, "
            f"flight={resolved:.3f} m"
        )
    except (KeyError, TypeError, ValueError) as exc:
        safety_ok = False
        safety_detail = f"invalid flat flight_plan: {exc}"
    checks.append(("MuJoCo Flat ground/altitude contract", safety_ok, safety_detail))

    process_models = marker.get("process_models")
    observed_ids = []
    files_ok = isinstance(process_models, list) and len(process_models) == experiment.process_count
    details = []
    for process_model in process_models if isinstance(process_models, list) else []:
        ids = process_model.get("drone_ids", [])
        mjb = Path(str(process_model.get("mjb", "")))
        receipt = Path(str(process_model.get("receipt", "")))
        if isinstance(ids, list):
            observed_ids.extend(int(value) for value in ids)
        else:
            files_ok = False
            ids = []
        files_ok = files_ok and mjb.is_file() and receipt.is_file()
        details.append(
            f"p{process_model.get('process_index')}={len(ids)} drones, "
            f"mjb={'OK' if mjb.is_file() else 'NG'}"
        )
    coverage_ok = observed_ids == list(range(1, experiment.drone_count + 1))
    checks.append(
        (
            "MuJoCo Flat process models",
            files_ok and coverage_ok,
            "; ".join(details),
        )
    )
    type_config = Path(str(marker.get("type_config", "")))
    checks.append(("MuJoCo Flat Drone type config", type_config.is_file(), str(type_config)))
    try:
        checks.append(("Drone PRO service", True, str(base.resolve_drone_binary(drone_root, system_name))))
    except base.RecipeError as exc:
        checks.append(("Drone PRO service", False, str(exc)))
    if experiment.visualization:
        try:
            checks.append(("Drone PRO visual-state publisher", True, str(base.resolve_visual_state_publisher(drone_root, system_name))))
        except base.RecipeError as exc:
            checks.append(("Drone PRO visual-state publisher", False, str(exc)))
    if marker.get("drone_show", {}).get("ar", {}).get("enabled") is True:
        tls_root = paths.recipe_root / "ar-tls"
        certificate = tls_root / "hakoniwa-ar-server.crt"
        private_key = tls_root / "hakoniwa-ar-server.key"
        checks.append(
            (
                "AR HTTPS certificate",
                certificate.is_file() and private_key.is_file(),
                str(certificate),
            )
        )
        for port in (8443, 8766):
            available = base._port_available(port)
            if available is not None:
                checks.append(
                    (
                        f"AR port {port}",
                        available,
                        "available" if available else "in use",
                    )
                )
    return checks


base._mujoco_city_runtime_checks = _show_mujoco_runtime_checks


def _show_definition(experiment_path: Path) -> tuple[Path, dict]:
    raw = _BASE_LOAD_SIMPLE_YAML(experiment_path)
    scenario = raw.get("scenario")
    value = scenario.get("show_file") if isinstance(scenario, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise base.RecipeError("scenario.show_file must be a non-empty relative path")
    candidate = Path(value)
    if candidate.is_absolute():
        raise base.RecipeError("scenario.show_file must be relative to the experiment")
    path = (experiment_path.resolve().parent / candidate).resolve()
    try:
        definition = load_show_file(path)
    except ShowFileError as exc:
        raise base.RecipeError(str(exc)) from exc
    for formation in definition["formations"]:
        svg_path = (path.parent / formation["svg"]).resolve()
        if not svg_path.is_file():
            raise base.RecipeError(f"Formation SVG not found: {svg_path}")
    return path, definition


def _formation_scale_m(
    experiment_path: Path, override: float | None = None
) -> float:
    if override is not None:
        if not math.isfinite(override) or override <= 0:
            raise base.RecipeError("--formation-scale must be positive")
        return float(override)
    raw = _BASE_LOAD_SIMPLE_YAML(experiment_path)
    scenario = raw.get("scenario")
    formation = scenario.get("formation") if isinstance(scenario, dict) else None
    if not isinstance(formation, dict):
        raise base.RecipeError("scenario.formation must be a mapping")
    unknown = sorted(set(formation) - {"scale_m", "audience_tilt_deg"})
    if unknown:
        raise base.RecipeError(
            "scenario.formation has unknown fields: " + ", ".join(unknown)
        )
    value = formation.get("scale_m")
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or not float(value) > 0
    ):
        raise base.RecipeError("scenario.formation.scale_m must be positive")
    return float(value)


def _formation_audience_tilt_deg(
    experiment_path: Path, override: float | None = None
) -> float:
    if override is not None:
        value = override
    else:
        raw = _BASE_LOAD_SIMPLE_YAML(experiment_path)
        scenario = raw.get("scenario")
        formation = scenario.get("formation") if isinstance(scenario, dict) else None
        if not isinstance(formation, dict):
            raise base.RecipeError("scenario.formation must be a mapping")
        value = formation.get("audience_tilt_deg", 15.0)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or not -85.0 <= float(value) <= 85.0
    ):
        raise base.RecipeError(
            "scenario.formation.audience_tilt_deg must be between -85 and 85"
        )
    return float(value)


def _max_speed_m_s(experiment_path: Path) -> float:
    raw = _BASE_LOAD_SIMPLE_YAML(experiment_path)
    scenario = raw.get("scenario")
    value = scenario.get("max_speed_m_s") if isinstance(scenario, dict) else None
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or not float(value) > 0
    ):
        raise base.RecipeError("scenario.max_speed_m_s must be positive")
    return float(value)


def _viewer_settings(experiment_path: Path) -> dict:
    raw = _BASE_LOAD_SIMPLE_YAML(experiment_path)
    viewer = raw.get("viewer")
    if viewer is None:
        return {
            "initial_mode": "free",
            "network": {"host": _DEFAULT_VIEWER_HOST},
        }
    if not isinstance(viewer, dict):
        raise base.RecipeError("viewer must be a mapping")
    unknown = sorted(
        set(viewer)
        - {"initial_mode", "audience_camera", "led_appearance", "network"}
    )
    if unknown:
        raise base.RecipeError("viewer has unknown fields: " + ", ".join(unknown))
    initial_mode = viewer.get("initial_mode", "free")
    if initial_mode not in {"free", "audience"}:
        raise base.RecipeError("viewer.initial_mode must be free or audience")
    network = viewer.get("network", {})
    if not isinstance(network, dict):
        raise base.RecipeError("viewer.network must be a mapping")
    unknown_network = sorted(set(network) - {"host"})
    if unknown_network:
        raise base.RecipeError(
            "viewer.network has unknown fields: " + ", ".join(unknown_network)
        )
    host = network.get("host", _DEFAULT_VIEWER_HOST)
    if not isinstance(host, str):
        raise base.RecipeError("viewer.network.host must be an IPv4 address")
    try:
        resolved_host = str(ipaddress.IPv4Address(host))
    except ipaddress.AddressValueError as exc:
        raise base.RecipeError(
            "viewer.network.host must be an IPv4 address"
        ) from exc
    settings = {
        "initial_mode": initial_mode,
        "network": {"host": resolved_host},
    }
    led_appearance = viewer.get("led_appearance")
    if led_appearance is not None:
        if not isinstance(led_appearance, dict):
            raise base.RecipeError("viewer.led_appearance must be a mapping")
        unknown_led = sorted(set(led_appearance) - {"scale", "intensity"})
        if unknown_led:
            raise base.RecipeError(
                "viewer.led_appearance has unknown fields: "
                + ", ".join(unknown_led)
            )
        resolved_led = {}
        for key, default in (("scale", 1.45), ("intensity", 1.25)):
            value = led_appearance.get(key, default)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or not 0.0 < float(value) <= 4.0
            ):
                raise base.RecipeError(
                    f"viewer.led_appearance.{key} must be within (0, 4]"
                )
            resolved_led[key] = float(value)
        settings["led_appearance"] = resolved_led
    camera = viewer.get("audience_camera")
    if initial_mode == "audience" and not isinstance(camera, dict):
        raise base.RecipeError(
            "viewer.audience_camera is required when initial_mode is audience"
        )
    if camera is None:
        return settings
    unknown_camera = sorted(
        set(camera) - {"position_m", "yaw_deg", "pitch_deg", "fov_deg"}
    )
    if unknown_camera:
        raise base.RecipeError(
            "viewer.audience_camera has unknown fields: "
            + ", ".join(unknown_camera)
        )
    position = camera.get("position_m")
    if (
        not isinstance(position, list)
        or len(position) != 3
        or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            for value in position
        )
    ):
        raise base.RecipeError(
            "viewer.audience_camera.position_m must contain three finite numbers"
        )
    resolved = {}
    for key in ("yaw_deg", "pitch_deg", "fov_deg"):
        value = camera.get(key)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
        ):
            raise base.RecipeError(
                f"viewer.audience_camera.{key} must be a finite number"
            )
        resolved[key] = float(value)
    if not -85.0 <= resolved["pitch_deg"] <= 85.0:
        raise base.RecipeError(
            "viewer.audience_camera.pitch_deg must be between -85 and 85"
        )
    if not 25.0 <= resolved["fov_deg"] <= 90.0:
        raise base.RecipeError(
            "viewer.audience_camera.fov_deg must be between 25 and 90"
        )
    settings["audience_camera"] = {
        "position_m": [float(value) for value in position],
        **resolved,
    }
    return settings


def _ar_settings(experiment_path: Path) -> dict:
    raw = _BASE_LOAD_SIMPLE_YAML(experiment_path)
    ar = raw.get("ar", {})
    if not isinstance(ar, dict):
        raise base.RecipeError("ar must be a mapping")
    unknown = sorted(set(ar) - {"enabled", "venue", "preview"})
    if unknown:
        raise base.RecipeError("ar has unknown fields: " + ", ".join(unknown))
    enabled = ar.get("enabled", False)
    if not isinstance(enabled, bool):
        raise base.RecipeError("ar.enabled must be boolean")
    if not enabled:
        return {"enabled": False}

    def coordinate(mapping, prefix):
        if not isinstance(mapping, dict):
            raise base.RecipeError(f"{prefix} must be a mapping")
        unknown_coordinate = sorted(set(mapping) - {"latitude", "longitude"})
        if unknown_coordinate:
            raise base.RecipeError(
                f"{prefix} has unknown fields: " + ", ".join(unknown_coordinate)
            )
        latitude = mapping.get("latitude")
        longitude = mapping.get("longitude")
        if (
            not isinstance(latitude, (int, float))
            or isinstance(latitude, bool)
            or not math.isfinite(float(latitude))
            or not -90.0 <= float(latitude) <= 90.0
        ):
            raise base.RecipeError(f"{prefix}.latitude must be within [-90, 90]")
        if (
            not isinstance(longitude, (int, float))
            or isinstance(longitude, bool)
            or not math.isfinite(float(longitude))
            or not -180.0 <= float(longitude) <= 180.0
        ):
            raise base.RecipeError(f"{prefix}.longitude must be within [-180, 180]")
        return {"latitude": float(latitude), "longitude": float(longitude)}

    venue = ar.get("venue")
    if not isinstance(venue, dict):
        raise base.RecipeError("ar.venue must be a mapping")
    unknown_venue = sorted(set(venue) - {"latitude", "longitude", "heading_deg"})
    if unknown_venue:
        raise base.RecipeError(
            "ar.venue has unknown fields: " + ", ".join(unknown_venue)
        )
    venue_coordinate = coordinate(
        {key: venue.get(key) for key in ("latitude", "longitude")},
        "ar.venue",
    )
    heading = venue.get("heading_deg", 0.0)
    if (
        not isinstance(heading, (int, float))
        or isinstance(heading, bool)
        or not math.isfinite(float(heading))
    ):
        raise base.RecipeError("ar.venue.heading_deg must be finite")

    preview = ar.get("preview", {})
    if not isinstance(preview, dict):
        raise base.RecipeError("ar.preview must be a mapping")
    unknown_preview = sorted(
        set(preview)
        - {
            "location_source",
            "override",
            "eye_height_m",
            "movement_speed_m_s",
            "device_orientation",
        }
    )
    if unknown_preview:
        raise base.RecipeError(
            "ar.preview has unknown fields: " + ", ".join(unknown_preview)
        )
    location_source = preview.get("location_source", "device")
    if location_source not in {"device", "override"}:
        raise base.RecipeError(
            "ar.preview.location_source must be device or override"
        )
    override = preview.get("override")
    resolved_override = (
        coordinate(override, "ar.preview.override")
        if override is not None
        else None
    )
    if location_source == "override" and resolved_override is None:
        raise base.RecipeError(
            "ar.preview.override is required when location_source is override"
        )
    eye_height = preview.get("eye_height_m", 1.6)
    if (
        not isinstance(eye_height, (int, float))
        or isinstance(eye_height, bool)
        or not math.isfinite(float(eye_height))
        or not 0.0 < float(eye_height) <= 10.0
    ):
        raise base.RecipeError("ar.preview.eye_height_m must be within (0, 10]")
    movement_speed = preview.get("movement_speed_m_s", 5.0)
    if (
        not isinstance(movement_speed, (int, float))
        or isinstance(movement_speed, bool)
        or not math.isfinite(float(movement_speed))
        or not 0.0 < float(movement_speed) <= 100.0
    ):
        raise base.RecipeError(
            "ar.preview.movement_speed_m_s must be within (0, 100]"
        )
    orientation = preview.get("device_orientation", "optional")
    if orientation not in {"off", "optional"}:
        raise base.RecipeError(
            "ar.preview.device_orientation must be off or optional"
        )
    return {
        "enabled": True,
        "venue": {**venue_coordinate, "heading_deg": float(heading) % 360.0},
        "preview": {
            "location_source": location_source,
            "override": resolved_override,
            "eye_height_m": float(eye_height),
            "movement_speed_m_s": float(movement_speed),
            "device_orientation": orientation,
        },
    }


def _map_viewer_url_base(experiment_path: Path) -> str:
    raw = _BASE_LOAD_SIMPLE_YAML(experiment_path)
    viewer = raw.get("viewer")
    has_explicit_network = (
        isinstance(viewer, dict) and "network" in viewer
    )
    if has_explicit_network:
        host = _viewer_settings(experiment_path)["network"]["host"]
    else:
        host = _DEFAULT_VIEWER_HOST
        try:
            foundation = base.load_foundation_module()
            paths = foundation.resolve_workspace(base.ROOT, base.RECIPE_ID)
            marker_path = _runtime_marker_path(paths)
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            host = marker["drone_show"]["viewer"]["network"]["host"]
            host = str(ipaddress.IPv4Address(host))
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass
    return (
        f"http://{host}:8000/drone-show/index.html"
        "?threejsRoot=/thirdparty/hakoniwa-threejs-drone"
        "&viewerConfigName=viewer-config-fleets.json"
    )


def _viewer_url(experiment_path: Path, drone_count: int) -> str:
    return (
        f"{_map_viewer_url_base(experiment_path)}"
        f"&dynamicSpawn=true&templateDroneIndex=0"
        f"&maxDynamicDrones={drone_count}"
    )


def _open_viewer(
    experiment_path: Path, *, drone_count_override: int | None = None
) -> int:
    requested = base.resolve_experiment(
        experiment_path, drone_count_override=drone_count_override
    )
    if not requested.visualization:
        raise base.RecipeError(
            "runtime.visualization=false; this headless experiment does not start "
            "VSP, WebBridge, or the Three.js viewer"
        )
    return (
        0
        if base.open_browser(_viewer_url(experiment_path, requested.drone_count))
        else 1
    )


def _open_ar_viewer(experiment_path: Path) -> int:
    ar = _ar_settings(experiment_path)
    if ar.get("enabled") is not True:
        raise base.RecipeError("ar.enabled=false; AR Viewer is unavailable")
    map_url = _map_viewer_url_base(experiment_path)
    host = map_url.split("//", 1)[1].split(":", 1)[0]
    return (
        0
        if base.open_browser(
            f"https://{host}:8443/drone-show/ar/index.html"
        )
        else 1
    )


def _load_base_compatible_experiment(path: Path):
    """Adapt the Show-facing scale to the generic word Recipe contract."""

    raw = _BASE_LOAD_SIMPLE_YAML(path)
    _environment_settings(path)
    _ar_settings(path)
    viewer = raw.get("viewer")
    if viewer is not None:
        _viewer_settings(path)
    scenario = raw.get("scenario")
    if not isinstance(scenario, dict) or "formation" not in scenario:
        compatible = copy.deepcopy(raw)
        compatible.pop("viewer", None)
        compatible.pop("environment", None)
        compatible.pop("ar", None)
        return compatible
    formation_scale_m = _formation_scale_m(path)
    _formation_audience_tilt_deg(path)
    maximum_speed_m_s = _max_speed_m_s(path)
    _, show_definition = _show_definition(path)
    compatibility_fields = sorted(
        set(scenario) & _INTERNAL_COMPATIBILITY_FIELDS
    )
    if compatibility_fields:
        raise base.RecipeError(
            "scenario.formation cannot be combined with internal compatibility fields: "
            + ", ".join(compatibility_fields)
        )
    compatible = copy.deepcopy(raw)
    compatible.pop("viewer", None)
    compatible.pop("environment", None)
    compatible.pop("ar", None)
    compatible_scenario = compatible["scenario"]
    del compatible_scenario["formation"]
    del compatible_scenario["max_speed_m_s"]
    del compatible_scenario["show_file"]
    compatible_scenario.update(_BASE_SCENARIO_COMPATIBILITY)
    compatibility_scale = formation_scale_m / _LEGACY_BASE_FORMATION_SCALE_M
    compatible_scenario.update(
        {
            key: value * compatibility_scale
            for key, value in _LEGACY_BASE_WORD_DIMENSIONS.items()
        }
    )
    # The generic Recipe requires speed_m_s. In Show IR mode this value is
    # forwarded as a maximum speed constraint, not as an independent timeline.
    compatible_scenario["speed_m_s"] = maximum_speed_m_s
    first_step = show_definition["timeline"][0]
    # The generic City Recipe still requires a three-phase compatibility
    # scenario. Runtime timing is owned by the external Show File.
    compatible_scenario["duration_sec"] = first_step["transition_sec"]
    compatible_scenario["hold_sec"] = first_step["hold_sec"]
    return compatible


# Business Pack still builds a compatibility HAKONIWA scenario. Keep that
# private adapter at the operator boundary; the public Show configuration owns
# only the final Formation's absolute maximum span.
base.load_simple_yaml = _load_base_compatible_experiment


def _write_show_launcher(
    paths,
    drone_root: Path,
    viewer_root: Path,
    experiment,
    system_name: str,
) -> Path:
    """Apply the Show-owned runtime extension after generic materialization."""

    if not experiment.visualization:
        raise base.RecipeError(
            "the browser-gated Drone Show requires runtime.visualization=true"
        )
    marker_path = _runtime_marker_path(paths)
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    runtime_viewer_root = viewer_root
    if marker.get("backend") == "mujoco-flat":
        runtime_viewer_root = show_runtime.materialize_flat_viewer(
            viewer_root=viewer_root,
            web_root=paths.recipe_root / "web" / "map-viewer",
            marker_path=marker_path,
        )
    launcher = _BASE_WRITE_LAUNCHER(
        paths, drone_root, runtime_viewer_root, experiment, system_name
    )
    # ``doctor`` and ``start`` regenerate the Launcher without necessarily
    # running ``configure`` first. Keep the Show-owned SHM slots present for
    # those entry points as well as for a fresh configure.
    show_runtime.extend_asset_pdudef(
        paths.recipe_config / "pdudef" / "drone-pdudef-current.json"
    )
    bridge_root = show_runtime.materialize_bridge_config(
        base.bridge_config_root(paths),
        paths.recipe_config / "web-bridge-drone-show",
    )
    show_runtime.materialize_browser(
        show_root=SHOW_ROOT,
        web_root=paths.recipe_root / "web" / "map-viewer",
        marker_path=marker_path,
        show_ir_path=paths.recipe_config
        / "scenario"
        / "show-ir"
        / "show-ir.json",
    )
    ar_tls = None
    if marker.get("drone_show", {}).get("ar", {}).get("enabled") is True:
        host = marker["drone_show"]["viewer"]["network"]["host"]
        ar_tls = _prepare_ar_tls(paths.recipe_root, host)
        public_ca = (
            paths.recipe_root
            / "web"
            / "map-viewer"
            / "drone-show"
            / "ar"
            / "hakoniwa-ar-ca.crt"
        )
        public_ca.write_bytes(ar_tls["ca_certificate"].read_bytes())
    return show_runtime.patch_launcher(
        launcher,
        show_runner=SHOW_ROOT / "tools" / "show_experience_runner.py",
        drone_root=drone_root,
        bridge_config_root=bridge_root,
        no_cache_http_server=SHOW_ROOT / "tools" / "no_cache_http_server.py",
        show_ir_path=paths.recipe_config
        / "scenario"
        / "show-ir"
        / "show-ir.json",
        show_ir_max_speed_m_s=experiment.speed_m_s,
        ar_gateway=(
            SHOW_ROOT / "tools" / "ar_https_gateway.py"
            if ar_tls is not None
            else None
        ),
        ar_certificate=(
            ar_tls["server_certificate"] if ar_tls is not None else None
        ),
        ar_private_key=(ar_tls["server_key"] if ar_tls is not None else None),
    )


base.write_launcher = _write_show_launcher


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Private City-backed Hakoniwa virtual drone show operator"
    )
    result.add_argument(
        "command",
        choices=[
            "prepare-native",
            "prepare-viewer",
            "configure",
            "doctor",
            "start",
            "status",
            "smoke",
            "open-viewer",
            "open-ar",
            "stop",
        ],
    )
    result.add_argument("--experiment", type=Path)
    result.add_argument("--drone-root", type=Path)
    result.add_argument("--viewer-root", type=Path)
    result.add_argument("--mujoco-city-world", type=Path)
    result.add_argument("--timeout-sec", type=float, default=300.0)
    result.add_argument("--drone-count", type=int)
    result.add_argument("--process-count", type=int)
    result.add_argument("--spawn-altitude-m", type=float, default=0.20)
    result.add_argument("--spawn-spacing-m", type=float, default=1.0)
    result.add_argument(
        "--formation-scale",
        type=float,
        help="override scenario.formation.scale_m in meters",
    )
    result.add_argument("--formation-rotation-deg", type=float, default=90.0)
    result.add_argument(
        "--formation-tilt-deg",
        type=float,
        default=None,
        help="override scenario.formation.audience_tilt_deg",
    )
    result.add_argument(
        "--altitude-mode",
        choices=["route-clearance", "city-max-clearance"],
        default="route-clearance",
    )
    result.add_argument("--above-city-clearance-m", type=float, default=10.0)
    return result


def _experiment_path(command: str, requested: Path | None) -> Path:
    if requested is not None:
        return requested.expanduser().resolve()
    configured = base.configured_experiment_path()
    if command != "configure" and configured.is_file():
        return configured
    return DEFAULT_EXPERIMENT.resolve()


def _drone_root(command: str, requested: Path | None) -> Path:
    if requested is not None:
        return requested.expanduser().resolve()
    if command != "configure":
        try:
            foundation = base.load_foundation_module()
            paths = foundation.resolve_workspace(base.ROOT, base.RECIPE_ID)
            marker = json.loads(
                _runtime_marker_path(paths).read_text(encoding="utf-8")
            )
            configured = marker.get("drone_root")
            if isinstance(configured, str) and configured:
                return Path(configured).resolve()
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        configured = base.configured_drone_root()
        if configured is not None:
            return configured
    return (SHOW_ROOT.parent / "hakoniwa-drone-pro").resolve()


def _viewer_root(requested: Path | None) -> Path:
    if requested is not None:
        return requested.expanduser().resolve()
    return (SHOW_ROOT.parent / "hakoniwa-threejs-drone").resolve()


def _require_terminated_launcher_for_configure() -> None:
    foundation = base.load_foundation_module()
    paths = foundation.resolve_workspace(base.ROOT, base.RECIPE_ID)
    session = base.session_file(paths)
    if not session.is_file():
        return
    try:
        command = base._launcher_command(paths, platform.system(), "status")
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise base.RecipeError(
            f"configure refused: could not inspect Launcher session: {session}"
        ) from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise base.RecipeError(
            "configure refused: Launcher status check failed: "
            f"{detail}; session={session}"
        )
    try:
        status = json.loads(completed.stdout.strip().splitlines()[-1])
        state = status.get("state")
    except (IndexError, json.JSONDecodeError, AttributeError) as exc:
        raise base.RecipeError(
            f"configure refused: invalid Launcher status response: {session}"
        ) from exc
    if state != "TERMINATED":
        raise base.RecipeError(
            "configure refused: Launcher session must be TERMINATED "
            f"(current={state or 'UNKNOWN'}): {session}; "
            "run 'python3 tools/recipe/virtual_drone_show.py stop' first"
        )


def configure(args: argparse.Namespace, experiment_path: Path, drone_root: Path) -> int:
    _require_terminated_launcher_for_configure()
    environment = _environment_settings(experiment_path)
    if environment["mode"] == "plateau" and args.mujoco_city_world is None:
        raise base.RecipeError(
            "configure requires --mujoco-city-world in plateau mode"
        )
    city_world = (
        args.mujoco_city_world.expanduser().resolve()
        if args.mujoco_city_world is not None
        else None
    )
    formation_scale_m = _formation_scale_m(
        experiment_path, override=args.formation_scale
    )
    formation_audience_tilt_deg = _formation_audience_tilt_deg(
        experiment_path, override=args.formation_tilt_deg
    )
    show_definition_path, show_definition = _show_definition(experiment_path)
    viewer_settings = _viewer_settings(experiment_path)
    ar_settings = _ar_settings(experiment_path)
    rc = base.configure(
        experiment_path,
        drone_root,
        drone_count_override=args.drone_count,
        process_count_override=args.process_count,
    )
    if rc != 0:
        return rc
    experiment = base.resolve_experiment(
        experiment_path,
        drone_count_override=args.drone_count,
        process_count_override=args.process_count,
    )
    foundation = base.load_foundation_module()
    paths = foundation.resolve_workspace(base.ROOT, base.RECIPE_ID)
    city_marker_path = paths.recipe_config / _CITY_MARKER_NAME
    flat_marker_path = paths.recipe_config / _FLAT_MARKER_NAME
    flat_marker_path.unlink(missing_ok=True)
    if environment["mode"] == "plateau":
        assert city_world is not None
        marker = city.configure_single_host_fleet(
            drone_root=drone_root,
            city_world_path=city_world,
            drone_count=experiment.drone_count,
            recipe_config=paths.recipe_config,
            spawn_altitude_m=args.spawn_altitude_m,
            spawn_spacing_m=args.spawn_spacing_m,
            altitude_mode=args.altitude_mode,
            above_city_clearance_m=args.above_city_clearance_m,
            process_count=experiment.process_count,
            formation_rotation_deg=args.formation_rotation_deg,
            formation_tilt_deg=formation_audience_tilt_deg,
        )
        marker_path = city_marker_path
    else:
        flat = environment["flat"]
        marker = city.configure_single_host_flat_fleet(
            drone_root=drone_root,
            drone_count=experiment.drone_count,
            recipe_config=paths.recipe_config,
            origin=flat["origin"],
            ground_height_m=flat["ground_height_m"],
            flight_altitude_agl_m=experiment.altitude_m,
            spawn_altitude_m=args.spawn_altitude_m,
            spawn_spacing_m=args.spawn_spacing_m,
            process_count=experiment.process_count,
            formation_rotation_deg=args.formation_rotation_deg,
            formation_tilt_deg=formation_audience_tilt_deg,
        )
        marker_path = flat_marker_path
    marker["drone_show"] = {
        "formation_scale_m": formation_scale_m,
        "max_speed_m_s": experiment.speed_m_s,
        "viewer": viewer_settings,
        "ar": ar_settings,
        "show_definition": {
            "path": str(show_definition_path),
            "sha256": hashlib.sha256(show_definition_path.read_bytes()).hexdigest(),
        },
    }
    marker_path.write_text(
        json.dumps(marker, indent=2) + "\n", encoding="utf-8"
    )
    show_runtime.extend_asset_pdudef(
        paths.recipe_config / "pdudef" / "drone-pdudef-current.json"
    )
    show_ir_path = show_runtime.materialize_show_ir(
        recipe_config=paths.recipe_config,
        marker=marker,
    )
    required_speed_m_s = show_runtime.validate_show_ir_speed_limit(
        show_ir_path,
        maximum_speed_m_s=experiment.speed_m_s,
        initial_altitude_m=float(marker["flight_plan"]["resolved_flight_altitude_m"]),
    )
    launcher = paths.recipe_config / "launcher.json"
    launcher.unlink(missing_ok=True)
    viewer_url = _viewer_url(experiment_path, experiment.drone_count)
    viewer_access = paths.recipe_root / "viewer-access"
    viewer_access.mkdir(parents=True, exist_ok=True)
    viewer_url_path = viewer_access / "viewer-url.txt"
    viewer_url_path.write_text(viewer_url + "\n", encoding="utf-8")
    viewer_qr_path = write_viewer_qr(
        viewer_access / "viewer-qr.svg", viewer_url
    )
    ar_url = None
    ar_qr_path = None
    ar_ca_path = None
    ar_ca_qr_path = None
    if ar_settings.get("enabled") is True:
        host = viewer_settings["network"]["host"]
        ar_tls = _prepare_ar_tls(paths.recipe_root, host)
        ar_url = f"https://{host}:8443/drone-show/ar/index.html"
        (viewer_access / "ar-viewer-url.txt").write_text(
            ar_url + "\n", encoding="utf-8"
        )
        ar_qr_path = write_viewer_qr(
            viewer_access / "ar-viewer-qr.svg", ar_url
        )
        ar_ca_path = viewer_access / "hakoniwa-ar-ca.crt"
        ar_ca_path.write_bytes(ar_tls["ca_certificate"].read_bytes())
        ar_ca_url = f"http://{host}:8000/drone-show/ar/hakoniwa-ar-ca.crt"
        ar_ca_qr_path = write_viewer_qr(
            viewer_access / "ar-ca-install-qr.svg", ar_ca_url
        )
    plan = marker["flight_plan"]
    print("Virtual drone show extension configured")
    print(f"Environment            : {environment['mode']}")
    if city_world is not None and environment["mode"] == "plateau":
        print(f"City World             : {city_world}")
    elif environment["mode"] == "flat":
        print(
            "Flat ground            : "
            f"Z={environment['flat']['ground_height_m']:g} m"
        )
    print(f"Drone PRO              : {drone_root}")
    print(f"MuJoCo process models  : {len(marker['process_models'])}")
    print(f"Formation scale        : {formation_scale_m:g} m")
    print(f"Formation audience tilt: {formation_audience_tilt_deg:g} deg")
    print(
        "Show File             : "
        f"{show_definition_path} ({len(show_definition['timeline'])} steps)"
    )
    print(
        "Show speed             : "
        f"required {required_speed_m_s:.3f} m/s / "
        f"maximum {experiment.speed_m_s:g} m/s"
    )
    print(f"Show IR                : {show_ir_path}")
    print(f"Mobile Viewer URL      : {viewer_url}")
    print(f"Mobile Viewer QR       : {viewer_qr_path}")
    if ar_url is not None:
        print(f"AR Viewer URL          : {ar_url}")
        print(f"AR Viewer QR           : {ar_qr_path}")
        print(f"AR trust certificate   : {ar_ca_path}")
        print(f"AR certificate QR      : {ar_ca_qr_path}")
    print(
        "Scenario               : takeoff -> "
        + " -> ".join(step["step_id"] for step in show_definition["timeline"])
        + " -> final hold"
    )
    print(
        "Flight altitude        : "
        f"{plan['resolved_flight_altitude_m']:.3f} m local Z"
    )
    print("Next:")
    print("  python tools/recipe/virtual_drone_show.py doctor")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        system_name = platform.system()
        if system_name not in base.SUPPORTED_NATIVE_SYSTEMS:
            raise base.RecipeError(f"unsupported native operating system: {system_name}")
        experiment_path = _experiment_path(args.command, args.experiment)
        drone_root = _drone_root(args.command, args.drone_root)
        viewer_root = _viewer_root(args.viewer_root)
        if args.command == "prepare-native":
            foundation = base.load_foundation_module()
            paths = foundation.resolve_workspace(base.ROOT, base.RECIPE_ID)
            return base.prepare_native_distribution(
                drone_root,
                system_name,
                cache_root=paths.work_root / "downloads",
                evidence_path=paths.recipe_validation / "native-distribution.json",
            )
        if args.command == "prepare-viewer":
            return base.prepare_viewer(viewer_root)
        if args.command == "configure":
            return configure(args, experiment_path, drone_root)
        if args.command == "doctor":
            return base.doctor(
                experiment_path,
                drone_root,
                viewer_root,
                drone_count_override=args.drone_count,
            )
        if args.command == "start":
            return base.start(
                experiment_path,
                drone_root,
                viewer_root,
                drone_count_override=args.drone_count,
            )
        if args.command == "status":
            return base.control(
                experiment_path,
                drone_root,
                "status",
                drone_count_override=args.drone_count,
            )
        if args.command == "stop":
            return base.control(
                experiment_path,
                drone_root,
                "terminate",
                drone_count_override=args.drone_count,
            )
        if args.command == "open-viewer":
            return _open_viewer(
                experiment_path, drone_count_override=args.drone_count
            )
        if args.command == "open-ar":
            return _open_ar_viewer(experiment_path)
        return base.smoke(
            experiment_path,
            args.timeout_sec,
            drone_count_override=args.drone_count,
        )
    except (
        base.RecipeError,
        city.FleetMujocoError,
        show_runtime.ShowRuntimeError,
        RuntimeError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
