import assert from 'node:assert/strict';
import { decodeFrame, encodeFrame, FRAME_SIZE, startCommand } from './show-pdu-codec.mjs';

const status = {
  schema_version: 1,
  protocol: 'hakoniwa.drone-show-control',
  kind: 'status',
  state: 'waiting',
  run_id: '1'.repeat(32),
  show_sha256: 'a'.repeat(64),
  sequence: 2,
  simulation_time_usec: 20000,
};
const command = startCommand(status, 1);
const encoded = encodeFrame(command);
assert.equal(encoded.byteLength, FRAME_SIZE);
assert.deepEqual(decodeFrame(encoded), command);
assert.equal(decodeFrame(new ArrayBuffer(FRAME_SIZE)), null);
assert.throws(() => decodeFrame(new ArrayBuffer(FRAME_SIZE - 1)), /1024/);
console.log('show-pdu-codec: ok');
