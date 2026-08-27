import assert from 'node:assert/strict';
import {
  applyOrientationDelta,
  normalizeAngleDeg,
  orientationSample,
  smoothOrientationPose,
} from './device-orientation.mjs';

assert.equal(normalizeAngleDeg(350), -10);
assert.equal(normalizeAngleDeg(-350), 10);
assert.deepEqual(
  orientationSample({ webkitCompassHeading: 120, beta: 80 }),
  { headingDeg: 120, betaDeg: 80 },
);
assert.deepEqual(
  applyOrientationDelta(
    { yawDeg: 90, pitchDeg: 10 },
    { headingDeg: 100, betaDeg: 80 },
    { headingDeg: 120, betaDeg: 70 },
  ),
  { yawDeg: 70, pitchDeg: 0 },
);
assert.deepEqual(
  smoothOrientationPose(null, { yawDeg: 30, pitchDeg: 20 }, 100, 1 / 60),
  { yawDeg: 30, pitchDeg: 20 },
);
const near = smoothOrientationPose(
  { yawDeg: 0, pitchDeg: 0 },
  { yawDeg: 10, pitchDeg: 10 },
  0,
  1 / 60,
);
const far = smoothOrientationPose(
  { yawDeg: 0, pitchDeg: 0 },
  { yawDeg: 10, pitchDeg: 10 },
  100,
  1 / 60,
);
assert.ok(near.yawDeg > far.yawDeg, 'near orientation should respond faster');
assert.deepEqual(
  smoothOrientationPose(
    { yawDeg: 5, pitchDeg: 5 },
    { yawDeg: 5.5, pitchDeg: 5.5 },
    100,
    1 / 60,
  ),
  { yawDeg: 5, pitchDeg: 5 },
  'far orientation should suppress small hand jitter',
);
console.log('device-orientation tests passed');
