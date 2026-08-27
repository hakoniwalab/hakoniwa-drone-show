const RAD2DEG = 180 / Math.PI;
const DEG2RAD = Math.PI / 180;

function finiteVector3(value, name) {
  if (!Array.isArray(value) || value.length !== 3
    || value.some((component) => !Number.isFinite(Number(component)))) {
    throw new TypeError(`${name} must contain three finite numbers`);
  }
  return value.map(Number);
}

function normalizeAngleDeg(value) {
  return ((value + 180) % 360 + 360) % 360 - 180;
}

export function rosPositionToEnu(positionRos) {
  const [forward, left, up] = finiteVector3(positionRos, 'positionRos');
  return [-left, forward, up];
}

export function centroidEnuFromDroneStates(states) {
  if (!Array.isArray(states) || states.length === 0) return null;
  const positions = states.map((state) => rosPositionToEnu(state.positionRos));
  return positions.reduce(
    (sum, position) => sum.map((value, axis) => value + position[axis]),
    [0, 0, 0],
  ).map((value) => value / positions.length);
}

export function centroidEnuFromShowFrame(showIr, frameIndex = 0) {
  const frames = showIr?.timeline;
  if (!Array.isArray(frames) || frames.length === 0) return null;
  const boundedIndex = Number.isSafeInteger(frameIndex)
    ? Math.max(0, Math.min(frameIndex, frames.length - 1))
    : 0;
  const states = frames[boundedIndex]?.states;
  if (!Array.isArray(states) || states.length === 0) return null;
  const positions = states.map((state) => finiteVector3(state.position_m, 'position_m'));
  return positions.reduce(
    (sum, position) => sum.map((value, axis) => value + position[axis]),
    [0, 0, 0],
  ).map((value) => value / positions.length);
}

export function directionGuide({
  observerPositionM,
  targetPositionM,
  yawDeg,
  pitchDeg,
  fovDeg,
  viewportWidth,
  viewportHeight,
  edgePaddingPx = 54,
}) {
  const observer = finiteVector3(observerPositionM, 'observerPositionM');
  const target = finiteVector3(targetPositionM, 'targetPositionM');
  const width = Number(viewportWidth);
  const height = Number(viewportHeight);
  if (!(width > 0) || !(height > 0)) throw new TypeError('viewport must be positive');

  const delta = target.map((value, axis) => value - observer[axis]);
  const horizontalDistanceM = Math.hypot(delta[0], delta[1]);
  const distanceM = Math.hypot(horizontalDistanceM, delta[2]);
  const targetYawDeg = Math.atan2(delta[1], delta[0]) * RAD2DEG;
  const targetPitchDeg = Math.atan2(delta[2], horizontalDistanceM) * RAD2DEG;
  const yawDeltaDeg = normalizeAngleDeg(targetYawDeg - Number(yawDeg));
  const pitchDeltaDeg = targetPitchDeg - Number(pitchDeg);
  const verticalFovDeg = Number(fovDeg);
  const horizontalFovDeg = 2 * Math.atan(
    Math.tan(verticalFovDeg * DEG2RAD / 2) * width / height,
  ) * RAD2DEG;
  // Positive ENU yaw turns the camera counter-clockwise, so a target with a
  // positive relative yaw appears on the left side of the screen.
  const xNormalized = -yawDeltaDeg / (horizontalFovDeg / 2);
  const yNormalized = -pitchDeltaDeg / (verticalFovDeg / 2);
  const inView = Math.abs(yawDeltaDeg) < 90
    && Math.abs(xNormalized) <= 1
    && Math.abs(yNormalized) <= 1;
  const clipScale = Math.max(1, Math.abs(xNormalized), Math.abs(yNormalized));
  const halfWidth = Math.max(1, width / 2 - edgePaddingPx);
  const halfHeight = Math.max(1, height / 2 - edgePaddingPx);
  const screenDx = xNormalized / clipScale * halfWidth;
  const screenDy = yNormalized / clipScale * halfHeight;

  return {
    distanceM,
    inView,
    leftPx: width / 2 + screenDx,
    topPx: height / 2 + screenDy,
    rotationDeg: Math.atan2(screenDy, screenDx) * RAD2DEG,
    yawDeltaDeg,
    pitchDeltaDeg,
  };
}

export function formatDistance(distanceM) {
  const distance = Math.max(0, Number(distanceM));
  if (distance < 1000) return `${Math.round(distance)} m`;
  if (distance < 10000) return `${(distance / 1000).toFixed(1)} km`;
  return `${Math.round(distance / 1000)} km`;
}

export function relativeObserverPosition({
  positionM,
  initialPositionM,
  initialYawDeg,
  groundHeightM,
}) {
  const position = finiteVector3(positionM, 'positionM');
  const initial = finiteVector3(initialPositionM, 'initialPositionM');
  const yawRad = Number(initialYawDeg) * DEG2RAD;
  const deltaEast = position[0] - initial[0];
  const deltaNorth = position[1] - initial[1];
  return {
    forwardM: deltaEast * Math.cos(yawRad) + deltaNorth * Math.sin(yawRad),
    rightM: deltaEast * Math.sin(yawRad) - deltaNorth * Math.cos(yawRad),
    heightM: position[2] - Number(groundHeightM),
  };
}

export function nearestDroneDistance(observerPositionM, states) {
  const observer = finiteVector3(observerPositionM, 'observerPositionM');
  if (!Array.isArray(states) || states.length === 0) return null;
  return Math.min(...states.map((state) => {
    const position = rosPositionToEnu(state.positionRos);
    return Math.hypot(...position.map((value, axis) => value - observer[axis]));
  }));
}
