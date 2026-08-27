export function normalizeAngleDeg(value) {
  let normalized = Number(value) % 360;
  if (normalized > 180) normalized -= 360;
  if (normalized <= -180) normalized += 360;
  return normalized;
}

export function orientationSample(event) {
  const heading = Number.isFinite(Number(event?.webkitCompassHeading))
    ? Number(event.webkitCompassHeading)
    : Number.isFinite(Number(event?.alpha))
      ? 360 - Number(event.alpha)
      : null;
  const beta = Number.isFinite(Number(event?.beta)) ? Number(event.beta) : null;
  if (heading == null || beta == null) return null;
  return { headingDeg: heading, betaDeg: beta };
}

export function applyOrientationDelta(basePose, baseline, current) {
  return {
    yawDeg: Number(basePose.yawDeg)
      - normalizeAngleDeg(current.headingDeg - baseline.headingDeg),
    pitchDeg: Math.max(
      -85,
      Math.min(85, Number(basePose.pitchDeg) + current.betaDeg - baseline.betaDeg),
    ),
  };
}

export function smoothOrientationPose(previous, target, distanceM, elapsedSec) {
  if (!previous) return { ...target };
  const distance = Math.max(0, Number(distanceM) || 0);
  const distanceFactor = distance / (distance + 20);
  const timeConstantSec = 0.08 + 0.38 * distanceFactor;
  const deadbandDeg = 0.12 + 0.75 * distanceFactor;
  const dt = Math.max(0.008, Math.min(0.1, Number(elapsedSec) || 1 / 60));
  const alpha = 1 - Math.exp(-dt / timeConstantSec);
  const filteredDelta = (delta) => (
    Math.abs(delta) <= deadbandDeg ? 0 : delta * alpha
  );
  const yawDelta = normalizeAngleDeg(Number(target.yawDeg) - Number(previous.yawDeg));
  const pitchDelta = Number(target.pitchDeg) - Number(previous.pitchDeg);
  return {
    yawDeg: normalizeAngleDeg(Number(previous.yawDeg) + filteredDelta(yawDelta)),
    pitchDeg: Math.max(
      -85,
      Math.min(85, Number(previous.pitchDeg) + filteredDelta(pitchDelta)),
    ),
  };
}

export async function requestDeviceOrientationPermission() {
  const api = globalThis.DeviceOrientationEvent;
  if (!api) throw new Error('この端末では姿勢センサーを利用できません');
  if (typeof api.requestPermission === 'function') {
    const result = await api.requestPermission();
    if (result !== 'granted') throw new Error('姿勢センサーの利用が許可されませんでした');
  }
  return true;
}
