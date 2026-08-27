import assert from 'node:assert/strict';
import { GlobalWindClient } from './global-wind-client.mjs';
import { decodeFrame } from './global-wind-protocol.mjs';

const calls = [];
const manager = {
  async declare_pdu_for_write(robot, pdu) {
    calls.push(['declare', robot, pdu]);
    return true;
  },
  async flush_pdu_raw_data(robot, pdu, frame) {
    calls.push(['send', robot, pdu, decodeFrame(frame)]);
    return true;
  },
};
const client = new GlobalWindClient(manager);
await client.start();
const first = await client.sendManual({ enabled: true, directionToDeg: 90, speedMps: 5, speedStddevMps: 1 });
const duplicate = await client.sendManual({ enabled: true, directionToDeg: 90, speedMps: 5, speedStddevMps: 1 });
const live = await client.sendLive({
  provider: 'open-meteo', validAt: '2026-08-28T00:00:00.000Z',
  vectorRosMS: [0, -5, 0], speedStddevMps: 1,
});
const off = await client.sendManual({ enabled: false, directionToDeg: 90, speedMps: 5, speedStddevMps: 1 });
assert.equal(first.sent, true);
assert.equal(duplicate.sent, false);
assert.equal(off.sent, true);
assert.equal(live.sent, true);
assert.deepEqual(calls[0], ['declare', 'DroneShow', 'global_wind_command']);
assert.equal(calls.length, 4);
assert.deepEqual(calls[1][3].wind.vector_ros_m_s, [0, -5, 0]);
assert.equal(calls[1][3].wind.variation.speed_stddev_m_s, 1);
assert.equal(calls[2][3].source.mode, 'live');
assert.equal(calls[3][3].wind.enabled, false);
console.log('global-wind-client tests: ok');
