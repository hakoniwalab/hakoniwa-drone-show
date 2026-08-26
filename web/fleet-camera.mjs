function finiteRosPosition(drone) {
  const position = drone?.latestPose?.rosPos;
  return Array.isArray(position) && position.length === 3 &&
    position.every((value) => Number.isFinite(value))
    ? position.map(Number)
    : null;
}

/**
 * Compute one fixed, diagonal overview of the initial fleet.
 * The result remains in Hakoniwa/ROS coordinates; the Viewer owns conversion
 * to Three.js coordinates.
 */
export function computeInitialFleetCamera(drones) {
  const positions = (Array.isArray(drones) ? drones : [])
    .map(finiteRosPosition)
    .filter(Boolean);
  if (positions.length === 0) return null;

  const mins = [...positions[0]];
  const maxs = [...positions[0]];
  for (const position of positions.slice(1)) {
    for (let axis = 0; axis < 3; axis += 1) {
      mins[axis] = Math.min(mins[axis], position[axis]);
      maxs[axis] = Math.max(maxs[axis], position[axis]);
    }
  }
  const center = mins.map((value, axis) => (value + maxs[axis]) / 2);
  const horizontalSpan = Math.max(maxs[0] - mins[0], maxs[1] - mins[1], 12);
  const verticalSpan = Math.max(maxs[2] - mins[2], 2);
  const distance = Math.max(20, horizontalSpan * 1.25, verticalSpan * 2.5);
  const target = [center[0], center[1], center[2] + Math.max(1.5, verticalSpan * 0.2)];
  const position = [
    target[0] - distance * 0.72,
    target[1] - distance * 0.72,
    target[2] + distance * 0.52,
  ];
  return { positionRos: position, targetRos: target, droneCount: positions.length };
}
