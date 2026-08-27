import assert from 'node:assert/strict';
import { geographicEnuToShowEnu, geodeticDeltaToEnu, initialAudiencePosition } from './geo.mjs';

const north = geodeticDeltaToEnu(
  { latitude: 35, longitude: 138 },
  { latitude: 35.001, longitude: 138 },
);
assert.ok(Math.abs(north.eastM) < 0.001);
assert.ok(north.northM > 111 && north.northM < 112);

const rotated = geographicEnuToShowEnu(10, 0, 90);
assert.ok(Math.abs(rotated.eastM) < 1e-9);
assert.ok(Math.abs(rotated.northM + 10) < 1e-9);

assert.deepEqual(
  initialAudiencePosition({
    venue: { latitude: 35, longitude: 138, headingDeg: 0 },
    observer: { latitude: 35, longitude: 138 },
    groundHeightM: 5.5,
    eyeHeightM: 1.6,
  }),
  [0, 0, 7.1],
);
console.log('ar-geo tests passed');
