import assert from 'node:assert/strict';
import {
  manualWindCommand,
  liveWindCommand,
  meteorologicalWindToRos,
  flowDirectionToRos,
  normalizeDirectionFromDeg,
  physicalWindKey,
  decodeFrame,
  encodeFrame,
} from './global-wind-protocol.mjs';

function close(actual, expected) {
  actual.forEach((value, index) => assert.ok(Math.abs(value - expected[index]) < 1e-9));
}

close(meteorologicalWindToRos(0, 5), [-5, 0, 0]);
close(meteorologicalWindToRos(90, 5), [0, 5, 0]);
close(meteorologicalWindToRos(180, 5), [5, 0, 0]);
close(meteorologicalWindToRos(270, 5), [0, -5, 0]);
close(flowDirectionToRos(0, 5), [5, 0, 0]);
close(flowDirectionToRos(90, 5), [0, -5, 0]);
close(flowDirectionToRos(180, 5), [-5, 0, 0]);
close(flowDirectionToRos(270, 5), [0, 5, 0]);
assert.equal(normalizeDirectionFromDeg(-90), 270);

const enabled = manualWindCommand({
  publisherId: 'browser-test', sequence: 1, enabled: true,
  directionToDeg: 45, speedMps: 4,
  speedStddevMps: 1.5,
});
assert.equal(enabled.schema, 'hakoniwa.drone-show/global-wind/v1');
assert.equal(enabled.wind.enabled, true);
assert.deepEqual(enabled.wind.variation, { speed_stddev_m_s: 1.5, seed: 1 });

const disabled = manualWindCommand({
  publisherId: 'browser-test', sequence: 2, enabled: false,
  directionToDeg: 45, speedMps: 4,
});
assert.deepEqual(disabled.wind.vector_ros_m_s, [0, 0, 0]);
assert.notEqual(physicalWindKey(enabled), physicalWindKey(disabled));
const frame = encodeFrame(enabled);
assert.equal(frame.byteLength, 1024);
assert.deepEqual(decodeFrame(frame), enabled);

const live = liveWindCommand({
  publisherId: 'browser-test', sequence: 3, provider: 'open-meteo',
  validAt: '2026-08-28T00:00:00.000Z', vectorRosMS: [-1.23456, 2.34567, 0],
  speedStddevMps: 0.5,
});
assert.deepEqual(live.wind.vector_ros_m_s, [-1.235, 2.346, 0]);
assert.notEqual(physicalWindKey(enabled), physicalWindKey(live));

console.log('global-wind-protocol: ok');
