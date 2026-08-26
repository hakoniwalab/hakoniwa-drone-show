#!/usr/bin/env python3
"""Operate the private City-backed virtual drone show Recipe.

The generic single-host fleet runtime stays in Hakoniwa Business Pack.  This
operator owns the PRO-only City show extension and materializes it into the
generic Recipe workspace after the base configuration has been generated.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
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

base.OPERATOR_COMMAND = "python ../hakoniwa-drone-show/tools/recipe/virtual_drone_show.py"
base.MAP_VIEWER_URL_BASE = (
    "http://127.0.0.1:8000/drone-show/index.html"
    "?threejsRoot=/thirdparty/hakoniwa-threejs-drone"
    "&viewerConfigName=viewer-config-fleets.json"
)
_BASE_WRITE_LAUNCHER = base.write_launcher


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
    launcher = _BASE_WRITE_LAUNCHER(
        paths, drone_root, viewer_root, experiment, system_name
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
        marker_path=paths.recipe_config / "mujoco-city-fleet.json",
        show_ir_path=paths.recipe_config
        / "scenario"
        / "show-ir"
        / "show-ir.json",
    )
    return show_runtime.patch_launcher(
        launcher,
        show_runner=SHOW_ROOT / "tools" / "show_experience_runner.py",
        drone_root=drone_root,
        bridge_config_root=bridge_root,
        show_ir_path=paths.recipe_config
        / "scenario"
        / "show-ir"
        / "show-ir.json",
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
    result.add_argument("--formation-scale", type=float)
    result.add_argument("--formation-rotation-deg", type=float, default=90.0)
    result.add_argument("--formation-tilt-deg", type=float, default=15.0)
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
    if args.mujoco_city_world is None:
        raise base.RecipeError("configure requires --mujoco-city-world")
    _require_terminated_launcher_for_configure()
    city_world = args.mujoco_city_world.expanduser().resolve()
    rc = base.configure(
        experiment_path,
        drone_root,
        drone_count_override=args.drone_count,
        process_count_override=args.process_count,
        formation_scale_override=args.formation_scale,
    )
    if rc != 0:
        return rc
    experiment = base.resolve_experiment(
        experiment_path,
        drone_count_override=args.drone_count,
        process_count_override=args.process_count,
        formation_scale_override=args.formation_scale,
    )
    foundation = base.load_foundation_module()
    paths = foundation.resolve_workspace(base.ROOT, base.RECIPE_ID)
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
        formation_tilt_deg=args.formation_tilt_deg,
    )
    show_runtime.extend_asset_pdudef(
        paths.recipe_config / "pdudef" / "drone-pdudef-current.json"
    )
    show_ir_path = show_runtime.materialize_show_ir(
        recipe_config=paths.recipe_config,
        marker=marker,
    )
    launcher = paths.recipe_config / "launcher.json"
    launcher.unlink(missing_ok=True)
    plan = marker["flight_plan"]
    phases = plan.get("show_phases", ["HAKONIWA"])
    print("Virtual drone show extension configured")
    print(f"City World             : {city_world}")
    print(f"Drone PRO              : {drone_root}")
    print(f"MuJoCo process models  : {len(marker['process_models'])}")
    print(f"Show IR                : {show_ir_path}")
    print("Scenario               : takeoff -> " + " -> ".join(phases) + " -> final hold")
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
            return base.open_viewer(
                experiment_path, drone_count_override=args.drone_count
            )
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
