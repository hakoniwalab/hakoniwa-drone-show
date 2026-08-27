import assert from 'node:assert/strict';
import {
  centroidEnuFromDroneStates,
  centroidEnuFromShowFrame,
  directionGuide,
  formatDistance,
  nearestDroneDistance,
  relativeObserverPosition,
  rosPositionToEnu,
} from './direction-guide.mjs';

assert.deepEqual(rosPositionToEnu([20, -10, 5]), [10, 20, 5]);
assert.deepEqual(centroidEnuFromDroneStates([
  { positionRos: [10, -2, 4] },
  { positionRos: [20, -6, 8] },
]), [4, 15, 6]);
assert.deepEqual(centroidEnuFromShowFrame({
  timeline: [{ states: [{ position_m: [0, 2, 4] }, { position_m: [4, 6, 8] }] }],
}), [2, 4, 6]);

const ahead = directionGuide({
  observerPositionM: [0, 0, 0],
  targetPositionM: [100, 0, 0],
  yawDeg: 0,
  pitchDeg: 0,
  fovDeg: 60,
  viewportWidth: 400,
  viewportHeight: 800,
});
assert.equal(ahead.inView, true);
assert.equal(ahead.leftPx, 200);
assert.equal(ahead.topPx, 400);
assert.equal(ahead.distanceM, 100);

const left = directionGuide({
  observerPositionM: [0, 0, 0],
  targetPositionM: [0, 100, 0],
  yawDeg: 0,
  pitchDeg: 0,
  fovDeg: 60,
  viewportWidth: 400,
  viewportHeight: 800,
});
assert.equal(left.inView, false);
assert.ok(left.leftPx < 200);
assert.equal(Math.abs(Math.round(left.rotationDeg)), 180);
assert.equal(formatDistance(875), '875 m');
assert.equal(formatDistance(1520), '1.5 km');
assert.equal(formatDistance(12000), '12 km');
const relative = relativeObserverPosition({
  positionM: [13, 24, 8],
  initialPositionM: [10, 20, 5],
  initialYawDeg: 90,
  groundHeightM: 2,
});
assert.ok(Math.abs(relative.forwardM - 4) < 1e-12);
assert.ok(Math.abs(relative.rightM - 3) < 1e-12);
assert.equal(relative.heightM, 6);
assert.equal(nearestDroneDistance([0, 0, 0], [
  { positionRos: [3, 4, 0] },
  { positionRos: [0, 2, 0] },
]), 2);

console.log('AR direction-guide tests passed');
