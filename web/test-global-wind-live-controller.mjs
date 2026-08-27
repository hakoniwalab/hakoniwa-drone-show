import assert from 'node:assert/strict';
import { GlobalWindLiveController } from './global-wind-live-controller.mjs';

const result = {
  provider: 'open-meteo', validAt: '2026-08-28T00:00:00.000Z',
  wind: { speedMS: 3, directionFromDeg: 90, directionToDeg: 270, gustMS: 5.8 },
};
const provider = {
  calls: 0,
  buildUrl: () => new URL('https://api.open-meteo.com/v1/forecast?latitude=34.687'),
  async fetchCurrentWind() { this.calls += 1; return { ...result, fetchedAt: `fetch-${this.calls}` }; },
  abort() {},
};
const commands = [];
const client = {
  async sendLive(command) { commands.push(command); return { sent: true, command }; },
};
let stddev = 0;
const states = [];
const controller = new GlobalWindLiveController({
  client, provider, venue: { latitude: 34.687, longitude: 135.526 },
  pollIntervalSec: 3600, staleAfterSec: 3600,
  getSpeedStddevMps: () => stddev,
  onState: (state) => states.push(state),
});

await controller.activate();
assert.equal(commands.length, 1);
assert.deepEqual(commands[0].vectorRosMS.map((v) => Math.round(v)), [0, 3, 0]);
await controller.refresh();
assert.equal(provider.calls, 2);
assert.equal(commands.length, 1);
stddev = 1.5;
await controller.setSpeedStddevMps();
assert.equal(commands.length, 2);
assert.equal(commands[1].speedStddevMps, 1.5);
assert.equal(states.at(-1).status, 'ok');
controller.deactivate();
assert.equal(states.at(-1).mode, 'manual');

console.log('global-wind-live-controller tests: ok');
