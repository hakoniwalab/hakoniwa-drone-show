import assert from 'node:assert/strict';
import {
  ledStatesForFrame,
  rgbCss,
  validateShowIrForViewer,
} from './show-led-timeline.mjs';

const showIr = {
  drone_ids: ['Drone-1', 'Drone-2'],
  timeline: [
    {
      states: [
        { drone_id: 'Drone-1', led: { rgb: [255, 0, 0], brightness: 1 } },
        { drone_id: 'Drone-2', led: { rgb: [0, 255, 0], brightness: 0.5 } },
      ],
    },
  ],
};

assert.equal(validateShowIrForViewer(showIr, 2), showIr);
assert.deepEqual(ledStatesForFrame(showIr, 0), [
  { droneId: 'Drone-1', rgb: [255, 0, 0], brightness: 1 },
  { droneId: 'Drone-2', rgb: [0, 255, 0], brightness: 0.5 },
]);
assert.equal(rgbCss([255, 220, 48]), 'rgb(255, 220, 48)');
assert.throws(() => ledStatesForFrame(showIr, 1), /out of range/);

console.log('show-led-timeline: validation and frame resolution ok');
