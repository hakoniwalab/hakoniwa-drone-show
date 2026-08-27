import assert from 'node:assert/strict';
import {
  cameraHeadingDisplay,
  cardinalDirectionJa,
  compassHeadingFromEnuYaw,
} from './camera-heading.mjs';

assert.equal(compassHeadingFromEnuYaw(90), 0);
assert.equal(compassHeadingFromEnuYaw(0), 90);
assert.equal(compassHeadingFromEnuYaw(-90), 180);
assert.equal(compassHeadingFromEnuYaw(180), 270);
assert.equal(cardinalDirectionJa(0), '北');
assert.equal(cardinalDirectionJa(90), '東');
assert.deepEqual(cameraHeadingDisplay(45), {
  headingDeg: 45,
  headingText: '045',
  cardinal: '北東',
});

console.log('camera-heading tests: ok');
