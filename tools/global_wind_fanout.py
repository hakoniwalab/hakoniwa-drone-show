"""Pure Global Wind to per-Drone Disturbance fan-out policy."""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from tools.global_wind_protocol import GlobalWindReceiverState


DISTURBANCE_PDU_NAME = "disturb"
NEUTRAL_TEMPERATURE_C = 15.0
NEUTRAL_SEA_LEVEL_ATM = 1.0
MAX_SAMPLED_WIND_SPEED_M_S = 100.0


class GlobalWindFanoutError(RuntimeError):
    pass


@dataclass(frozen=True)
class FanoutResult:
    changed: bool
    drone_count: int
    elapsed_msec: float


class GlobalWindFanout:
    """Own one pre-created Disturbance object per Drone and update on change."""

    def __init__(
        self,
        *,
        manager: Any,
        drone_names: Iterable[str],
        disturbance_factory: Callable[[], Any],
        disturbance_encoder: Callable[[Any], bytes | bytearray],
    ) -> None:
        names = tuple(drone_names)
        if not names or any(not isinstance(name, str) or not name for name in names):
            raise GlobalWindFanoutError("at least one valid Drone name is required")
        if len(set(names)) != len(names):
            raise GlobalWindFanoutError("Drone names must be unique")
        self.manager = manager
        self.drone_names = names
        self.disturbance_encoder = disturbance_encoder
        self.disturbances = {name: disturbance_factory() for name in names}
        self.receiver_state = GlobalWindReceiverState()
        self.current_enabled = False
        self.current_vector_ros_m_s = (0.0, 0.0, 0.0)
        self.current_speed_stddev_m_s = 0.0
        self.current_variation_seed = 1
        for disturbance in self.disturbances.values():
            disturbance.d_temp.value = NEUTRAL_TEMPERATURE_C
            disturbance.d_atm.sea_level_atm = NEUTRAL_SEA_LEVEL_ATM
            self._set_disturbance_wind(disturbance, self.current_vector_ros_m_s)

    @staticmethod
    def _set_disturbance_wind(
        disturbance: Any, vector_ros_m_s: Iterable[float]
    ) -> None:
        x_ros, y_ros, z_ros = (float(value) for value in vector_ros_m_s)
        disturbance.d_wind.value.x = x_ros
        disturbance.d_wind.value.y = y_ros
        disturbance.d_wind.value.z = z_ros

    @staticmethod
    def _standard_normal(drone_name: str, seed: int) -> float:
        digest = hashlib.sha256(f"{seed}:{drone_name}".encode("utf-8")).digest()
        denominator = float((1 << 64) + 1)
        u1 = (int.from_bytes(digest[:8], "big") + 1) / denominator
        u2 = (int.from_bytes(digest[8:16], "big") + 1) / denominator
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

    def _vector_for_drone(self, drone_name: str) -> tuple[float, float, float]:
        mean_vector = self.current_vector_ros_m_s
        mean_speed = math.sqrt(sum(component * component for component in mean_vector))
        if (
            not self.current_enabled
            or mean_speed == 0.0
            or self.current_speed_stddev_m_s == 0.0
        ):
            return mean_vector
        sampled_speed = max(
            0.0,
            min(
                MAX_SAMPLED_WIND_SPEED_M_S,
                mean_speed
                + self.current_speed_stddev_m_s
                * self._standard_normal(drone_name, self.current_variation_seed),
            ),
        )
        scale = sampled_speed / mean_speed
        return tuple(component * scale for component in mean_vector)

    def _write_all(self) -> FanoutResult:
        started = time.perf_counter()
        failed: list[str] = []
        for name in self.drone_names:
            disturbance = self.disturbances[name]
            self._set_disturbance_wind(disturbance, self._vector_for_drone(name))
            payload = self.disturbance_encoder(disturbance)
            if not self.manager.flush_pdu_raw_data_nowait(
                name, DISTURBANCE_PDU_NAME, payload
            ):
                failed.append(name)
        elapsed_msec = (time.perf_counter() - started) * 1000.0
        if failed:
            preview = ", ".join(failed[:5])
            suffix = "..." if len(failed) > 5 else ""
            raise GlobalWindFanoutError(
                f"Disturbance write failed for {len(failed)} Drone(s): {preview}{suffix}"
            )
        return FanoutResult(True, len(self.drone_names), elapsed_msec)

    def initialize_default(self) -> FanoutResult:
        """Write the neutral no-wind state once after SHM has been loaded."""

        self.current_enabled = False
        self.current_vector_ros_m_s = (0.0, 0.0, 0.0)
        self.current_speed_stddev_m_s = 0.0
        self.current_variation_seed = 1
        return self._write_all()

    def accept(self, message: Any) -> FanoutResult:
        normalized, changed = self.receiver_state.accept(message)
        if not changed:
            return FanoutResult(False, 0, 0.0)
        wind = normalized["wind"]
        self.current_enabled = bool(wind["enabled"])
        self.current_vector_ros_m_s = tuple(
            float(value) for value in wind["vector_ros_m_s"]
        )
        variation = wind["variation"]
        self.current_speed_stddev_m_s = float(variation["speed_stddev_m_s"])
        self.current_variation_seed = int(variation["seed"])
        return self._write_all()

    def reapply_current(self) -> FanoutResult:
        """Reapply the retained physical state once after a Hakoniwa reset."""

        return self._write_all()


class GlobalWindAssetRuntime:
    """Lifecycle ordering shared by the executable and unit tests."""

    def __init__(self, *, manager: Any, fanout: GlobalWindFanout, endpoint: Any) -> None:
        self.manager = manager
        self.fanout = fanout
        self.endpoint = endpoint

    def initialize(self) -> FanoutResult:
        # run_nowait must precede the first write so Hakoniwa SHM slots are loaded.
        if not self.manager.run_nowait():
            raise GlobalWindFanoutError("initial Global Wind SHM load failed")
        result = self.fanout.initialize_default()
        self.endpoint.post_start()
        return result

    def reset(self) -> FanoutResult:
        if not self.manager.run_nowait():
            raise GlobalWindFanoutError("Global Wind SHM reload failed after reset")
        return self.fanout.reapply_current()
