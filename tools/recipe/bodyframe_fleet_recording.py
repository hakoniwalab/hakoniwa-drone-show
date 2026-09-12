#!/usr/bin/env python3
"""Run the measured 128-UAV BodyFrame Fleet with a browser START gate."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import subprocess
import sys
from pathlib import Path


SHOW_ROOT = Path(__file__).resolve().parents[2]
BUSINESS_PACK_ROOT = Path(
    __import__("os").environ.get("HAKONIWA_BUSINESS_PACK_ROOT", SHOW_ROOT.parent / "hakoniwa-business-pack")
).expanduser().resolve()
for path in (BUSINESS_PACK_ROOT, BUSINESS_PACK_ROOT / "tools", BUSINESS_PACK_ROOT / "tools" / "recipe", SHOW_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
# hakoniwa-drone-show owns the ``tools`` package.  Extend its package paths so
# the Business Pack's namespace-style helpers remain importable when this
# operator is run from the Drone Show checkout.
import tools
if str(BUSINESS_PACK_ROOT / "tools") not in tools.__path__:
    tools.__path__.append(str(BUSINESS_PACK_ROOT / "tools"))
import tools.recipe
if str(BUSINESS_PACK_ROOT / "tools" / "recipe") not in tools.recipe.__path__:
    tools.recipe.__path__.append(str(BUSINESS_PACK_ROOT / "tools" / "recipe"))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


base = _load_module(
    "business_pack_bodyframe_fleet_base",
    BUSINESS_PACK_ROOT / "tools" / "recipe" / "drone_fleet_single_host.py",
)
from tools.recipe import bodyframe_recording_runtime
from tools.recipe import show_runtime


RECIPE_ID = "drone-fleet-bodyframe-recording"
DEFAULT_EXPERIMENT = SHOW_ROOT / "recipes" / "experiments" / "bodyframe-fleet-recording-128.yaml"
OPERATOR_COMMAND = "python ../hakoniwa-drone-show/tools/recipe/bodyframe_fleet_recording.py"
_BASE_WRITE_LAUNCHER = base.write_launcher
base.RECIPE_ID = RECIPE_ID
base.OPERATOR_COMMAND = OPERATOR_COMMAND
base.DEFAULT_EXPERIMENT = DEFAULT_EXPERIMENT
# ``base.viewer_url()`` appends dynamic-spawn parameters with ``&``.
base.VIEWER_URL_BASE = "http://127.0.0.1:8000/recording/index.html?recording=1"
# The recording extension has its own workspace identity, while the native
# Drone Core distribution is intentionally validated against the established
# public single-host Fleet contract.
base.recipe_file = lambda: BUSINESS_PACK_ROOT / "recipes" / "examples" / "drone-fleet-single-host.yaml"


def _paths():
    return base.load_foundation_module().resolve_workspace(base.ROOT, RECIPE_ID)


def _clear_stale_session_if_orphaned(session: Path) -> bool:
    """Clear a stale Launcher record only after its recorded parent has exited."""

    try:
        payload = json.loads(session.read_text(encoding="utf-8"))
        pid = int(payload["pid"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise base.RecipeError(f"cannot safely recover stale recording session {session}: {exc}") from exc
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        session.unlink()
        print(f"[WARN] removed orphaned stale recording session: {session}")
        return True
    except PermissionError:
        pass
    raise base.RecipeError(
        f"recording Launcher process {pid} is still present although its session is STALE: {session}; run stop first"
    )


def _recording_viewer_root(paths, viewer_root: Path, experiment) -> Path:
    return bodyframe_recording_runtime.materialize_viewer(
        show_root=SHOW_ROOT,
        viewer_root=viewer_root,
        output_root=paths.recipe_root / "web" / "fleet-recording-viewer",
        drone_count=experiment.drone_count,
        process_count=experiment.process_count,
        formation=experiment.word,
        real_time_sync=experiment.show_runner_real_time_sync,
    )


def _write_launcher(paths, drone_root: Path, viewer_root: Path, experiment, system_name: str) -> Path:
    if not experiment.visualization:
        raise base.RecipeError("BodyFrame recording requires runtime.visualization=true")
    recording_viewer = _recording_viewer_root(paths, viewer_root, experiment)
    launcher = _BASE_WRITE_LAUNCHER(paths, drone_root, recording_viewer, experiment, system_name)
    pdu_config = paths.recipe_config / "pdudef" / "drone-pdudef-current.json"
    show_runtime.extend_asset_pdudef(pdu_config)
    bridge_root = show_runtime.materialize_bridge_config(
        base.bridge_config_root(paths), paths.recipe_config / "web-bridge-fleet-recording"
    )
    return show_runtime.patch_launcher(
        launcher,
        show_runner=SHOW_ROOT / "tools" / "show_experience_runner.py",
        drone_root=drone_root,
        bridge_config_root=bridge_root,
        no_cache_http_server=SHOW_ROOT / "tools" / "no_cache_http_server.py",
    )


base.write_launcher = _write_launcher


def _bodyframe_errors(paths, experiment) -> list[str]:
    errors: list[str] = []
    type_path = paths.recipe_config / "drone" / "fleets" / "types" / "api.json"
    try:
        physics = json.loads(type_path.read_text(encoding="utf-8"))["components"]["droneDynamics"]["physicsEquation"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        errors.append(f"invalid BodyFrame type config {type_path}: {exc}")
    else:
        if physics != "BodyFrame":
            errors.append(f"expected BodyFrame physics, got {physics!r}")
    expected = base.expected_partition_counts(experiment.drone_count, experiment.process_count)
    for index, count in enumerate(expected, start=1):
        path = paths.recipe_config / "drone" / "fleets" / f"api-current-part{index}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            drones = payload["drones"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"invalid partition {path}: {exc}")
            continue
        if len(drones) != count:
            errors.append(f"partition {index}: expected {count} drones, got {len(drones)}")
        if "api" not in payload.get("types", {}):
            errors.append(f"partition {index}: BodyFrame api type is missing")
    return errors


def configure(experiment_path: Path, drone_root: Path, viewer_root: Path, args: argparse.Namespace) -> int:
    experiment = base.resolve_experiment(
        experiment_path,
        drone_count_override=args.drone_count,
        process_count_override=args.process_count,
    )
    if experiment.measurement is not None:
        raise base.RecipeError("recording profile must not enable measurement")
    if (experiment.drone_count, experiment.process_count) != (128, 8):
        raise base.RecipeError("recording profile must use the measured 128-UAV / 8-process condition")
    foundation = base.load_foundation_module()
    paths = foundation.resolve_workspace(base.ROOT, RECIPE_ID)
    session = base.session_file(paths)
    if session.is_file():
        try:
            completed = subprocess.run(
                base._launcher_command(paths, platform.system(), "status"),
                env=base.runtime_environment(paths, drone_root, platform.system()),
                capture_output=True,
                text=True,
                check=False,
                timeout=5.0,
            )
            state = json.loads(completed.stdout.strip().splitlines()[-1]).get("state")
        except (OSError, subprocess.TimeoutExpired, IndexError, json.JSONDecodeError):
            state = "UNKNOWN"
        if state == "STALE":
            _clear_stale_session_if_orphaned(session)
        elif state != "TERMINATED":
            raise base.RecipeError(
                f"configure refused while recording session is {state}: {session}; run stop first"
            )
    foundation.prepare_workspace(paths)
    base.prepare_config(paths, drone_root, experiment)
    for name in ("mujoco-city-fleet.json", "mujoco-flat-fleet.json"):
        (paths.recipe_config / name).unlink(missing_ok=True)
    errors = _bodyframe_errors(paths, experiment)
    if errors:
        raise base.RecipeError("BodyFrame materialization failed: " + "; ".join(errors))
    base.write_simple_yaml(paths.recipe_config / "resolved-experiment.yaml", base.resolved_experiment_dict(experiment))
    base.write_foundation_requirements(paths.recipe_config / "foundation-requirements.yaml", experiment)
    (paths.recipe_config / "launcher.json").unlink(missing_ok=True)
    print(f"Recipe workspace       : {paths.recipe_root}")
    print("Physics backend        : BodyFrame (no MuJoCo world)")
    print("Measured condition     : 128 UAV / 8 processes / 16 UAV per process")
    print("Recording mode         : Browser START gate + real-time sync")
    print("Next:")
    print(f"  python {BUSINESS_PACK_ROOT / 'tools' / 'foundation.py'} doctor --recipe {paths.recipe_config / 'foundation-requirements.yaml'}")
    print(f"  {OPERATOR_COMMAND} doctor")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="BodyFrame 128-UAV recording Recipe")
    result.add_argument("command", choices=["prepare-native", "prepare-viewer", "configure", "doctor", "start", "status", "smoke", "open-viewer", "stop"])
    result.add_argument("--experiment", type=Path, default=DEFAULT_EXPERIMENT)
    result.add_argument("--drone-root", type=Path)
    result.add_argument("--viewer-root", type=Path)
    result.add_argument("--timeout-sec", type=float, default=300.0)
    result.add_argument("--drone-count", type=int)
    result.add_argument("--process-count", type=int)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        system_name = platform.system()
        if system_name not in base.SUPPORTED_NATIVE_SYSTEMS:
            raise base.RecipeError(f"unsupported native operating system: {system_name}")
        experiment_path = args.experiment.expanduser().resolve()
        drone_root = (args.drone_root or (SHOW_ROOT.parent / "hakoniwa-drone-core")).expanduser().resolve()
        viewer_root = (args.viewer_root or (SHOW_ROOT.parent / "hakoniwa-threejs-drone")).expanduser().resolve()
        paths = _paths()
        if args.command == "prepare-native":
            return base.prepare_native_distribution(drone_root, system_name, cache_root=paths.work_root / "downloads", evidence_path=paths.recipe_validation / "native-distribution.json")
        if args.command == "prepare-viewer":
            return base.prepare_viewer(viewer_root)
        if args.command == "configure":
            return configure(experiment_path, drone_root, viewer_root, args)
        if args.command == "doctor":
            errors = _bodyframe_errors(paths, base.resolve_experiment(experiment_path))
            if errors:
                for error in errors:
                    print(f"[NG] {error}")
                return 1
            return base.doctor(experiment_path, drone_root, viewer_root)
        if args.command == "start":
            return base.start(experiment_path, drone_root, viewer_root)
        if args.command == "status":
            return base.control(experiment_path, drone_root, "status")
        if args.command == "stop":
            return base.control(experiment_path, drone_root, "terminate")
        if args.command == "open-viewer":
            return base.open_viewer(experiment_path)
        return base.smoke(experiment_path, args.timeout_sec)
    except base.RecipeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
