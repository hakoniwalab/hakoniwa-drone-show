export function normalizeDegrees(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  return ((number % 360) + 360) % 360;
}

export function compassHeadingFromEnuYaw(yawDeg) {
  return normalizeDegrees(90 - Number(yawDeg));
}

export function cardinalDirectionJa(headingDeg) {
  const labels = ['北', '北東', '東', '南東', '南', '南西', '西', '北西'];
  return labels[Math.round(normalizeDegrees(headingDeg) / 45) % labels.length];
}

export function cameraHeadingDisplay(yawDeg) {
  const headingDeg = compassHeadingFromEnuYaw(yawDeg);
  return {
    headingDeg,
    headingText: headingDeg.toFixed(0).padStart(3, '0'),
    cardinal: cardinalDirectionJa(headingDeg),
  };
}
