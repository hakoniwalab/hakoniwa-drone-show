import assert from 'node:assert/strict';
import { computeInitialFleetCamera } from './fleet-camera.mjs';

const drone = (x, y, z) => ({ latestPose: { rosPos: [x, y, z] } });

assert.equal(computeInitialFleetCamera([]), null);
assert.equal(computeInitialFleetCamera([{ latestPose: null }]), null);

const view = computeInitialFleetCamera([
  drone(-10, -5, 0.2),
  drone(10, 5, 0.2),
]);
assert.equal(view.droneCount, 2);
assert.deepEqual(view.targetRos, [0, 0, 1.7]);
assert.ok(view.positionRos[0] < view.targetRos[0]);
assert.ok(view.positionRos[1] < view.targetRos[1]);
assert.ok(view.positionRos[2] > view.targetRos[2]);

console.log('fleet-camera: ok');
