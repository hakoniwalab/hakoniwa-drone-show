import assert from 'node:assert/strict';
import {
  audienceCameraYaml,
  displayAudienceCameraState,
  normalizeAudienceCameraState,
} from './audience-camera-config.mjs';

const state = {
  enabled: true,
  positionM: [12.444, -36.805, -0.00001],
  yawDeg: 84.456,
  pitchDeg: 18.234,
  fovDeg: 52,
};

assert.deepEqual(displayAudienceCameraState(state), {
  x: '12.44',
  y: '-36.80',
  z: '0.00',
  yaw: '84.46',
  pitch: '18.23',
  fov: '52.00',
});
assert.equal(
  audienceCameraYaml(state),
  [
    '  audience_camera:',
    '    position_m: [12.44, -36.80, 0.00]',
    '    yaw_deg: 84.46',
    '    pitch_deg: 18.23',
    '    fov_deg: 52.00',
  ].join('\n'),
);
assert.throws(
  () => normalizeAudienceCameraState({ positionM: [0, 1], yawDeg: 0, pitchDeg: 0, fovDeg: 55 }),
  /unavailable/,
);

console.log('audience-camera-config: display and YAML formatting ok');
