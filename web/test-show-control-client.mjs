import assert from 'node:assert/strict';
import { ShowControlClient } from './show-control-client.mjs';
import { encodeFrame } from './show-pdu-codec.mjs';

const runA = '1'.repeat(32);
const runB = '2'.repeat(32);
const showHash = 'a'.repeat(64);
const status = (runId, sequence, state = 'waiting') => encodeFrame({
  schema_version: 1,
  protocol: 'hakoniwa.drone-show-control',
  kind: 'status',
  state,
  run_id: runId,
  show_sha256: showHash,
  sequence,
  simulation_time_usec: sequence * 20000,
});

let raw = null;
const accepted = [];
const manager = {
  read_pdu_raw_data: () => raw,
};
const config = {
  control: { robot_name: 'DroneShow', status_pdu_name: 'show_status' },
};
const client = new ShowControlClient(manager, config, (value) => accepted.push(value));

raw = status(runA, 30);
client.poll();
raw = status(runA, 29);
client.poll();
assert.deepEqual(accepted.map((value) => [value.run_id, value.sequence]), [[runA, 30]]);

raw = status(runB, 1);
client.poll();
assert.deepEqual(
  accepted.map((value) => [value.run_id, value.sequence]),
  [[runA, 30], [runB, 1]],
);
assert.equal(client.lastStatusRunId, runB);
assert.equal(client.lastStatusSequence, 1);

console.log('show-control-client: run transition ok');
