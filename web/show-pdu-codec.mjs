export const FRAME_SIZE = 1024;
export const HEADER_SIZE = 8;
export const MAX_JSON_BYTES = FRAME_SIZE - HEADER_SIZE;
export const PROTOCOL = 'hakoniwa.drone-show-control';
export const SCHEMA_VERSION = 1;

const MAGIC = [0x48, 0x44, 0x53, 0x31]; // HDS1
const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', { fatal: true });

function canonicalize(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalize).join(',')}]`;
  if (value !== null && typeof value === 'object') {
    return `{${Object.keys(value).sort().map(
      (key) => `${JSON.stringify(key)}:${canonicalize(value[key])}`,
    ).join(',')}}`;
  }
  return JSON.stringify(value);
}

function validateCommon(message) {
  if (message?.schema_version !== SCHEMA_VERSION || message?.protocol !== PROTOCOL) {
    throw new Error('unsupported Drone Show control protocol');
  }
  if (!/^[0-9a-f]{32}$/.test(message.run_id ?? '')) {
    throw new Error('invalid run_id');
  }
  if (!/^[0-9a-f]{64}$/.test(message.show_sha256 ?? '')) {
    throw new Error('invalid show_sha256');
  }
  if (!Number.isSafeInteger(message.sequence) || message.sequence < 1) {
    throw new Error('invalid sequence');
  }
}

export function validateMessage(message) {
  if (message === null || typeof message !== 'object' || Array.isArray(message)) {
    throw new Error('Drone Show message must be an object');
  }
  validateCommon(message);
  if (message.kind === 'command') {
    const fields = Object.keys(message).sort().join(',');
    const expected = [
      'kind', 'protocol', 'run_id', 'schema_version', 'sequence', 'show_sha256', 'type',
    ].sort().join(',');
    if (fields !== expected || message.type !== 'START') {
      throw new Error('invalid START command');
    }
  } else if (message.kind === 'status') {
    const states = new Set(['initializing', 'waiting', 'running', 'completed', 'failed']);
    if (!states.has(message.state)) throw new Error('invalid status state');
    if (!Number.isSafeInteger(message.simulation_time_usec) || message.simulation_time_usec < 0) {
      throw new Error('invalid simulation_time_usec');
    }
    const allowed = new Set([
      'schema_version', 'protocol', 'kind', 'state', 'run_id', 'show_sha256',
      'sequence', 'simulation_time_usec', 'error',
    ]);
    if (Object.keys(message).some((key) => !allowed.has(key))) {
      throw new Error('status contains an unknown field');
    }
    if (message.state === 'failed') {
      if (typeof message.error !== 'string' || message.error.length < 1 || message.error.length > 256) {
        throw new Error('failed status requires an error');
      }
    } else if (Object.hasOwn(message, 'error')) {
      throw new Error('error is valid only for failed status');
    }
  } else {
    throw new Error('invalid message kind');
  }
  return message;
}

export function encodeFrame(message) {
  validateMessage(message);
  const payload = encoder.encode(canonicalize(message));
  if (payload.byteLength > MAX_JSON_BYTES) {
    throw new Error(`Drone Show JSON exceeds ${MAX_JSON_BYTES} bytes`);
  }
  const frame = new Uint8Array(FRAME_SIZE);
  frame.set(MAGIC, 0);
  const view = new DataView(frame.buffer);
  view.setUint16(4, payload.byteLength, false);
  view.setUint16(6, 0, false);
  frame.set(payload, HEADER_SIZE);
  return frame.buffer;
}

export function decodeFrame(value) {
  const raw = value instanceof Uint8Array
    ? value
    : new Uint8Array(value.buffer ?? value, value.byteOffset ?? 0, value.byteLength);
  if (raw.byteLength !== FRAME_SIZE) {
    throw new Error(`Drone Show frame must contain ${FRAME_SIZE} bytes`);
  }
  if (raw.every((byte) => byte === 0)) return null;
  if (!MAGIC.every((byte, index) => raw[index] === byte)) {
    throw new Error('invalid Drone Show frame magic');
  }
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
  const payloadSize = view.getUint16(4, false);
  const flags = view.getUint16(6, false);
  if (flags !== 0 || payloadSize < 2 || payloadSize > MAX_JSON_BYTES) {
    throw new Error('invalid Drone Show frame header');
  }
  for (let index = HEADER_SIZE + payloadSize; index < raw.byteLength; index += 1) {
    if (raw[index] !== 0) throw new Error('non-zero frame padding');
  }
  const message = JSON.parse(decoder.decode(raw.slice(HEADER_SIZE, HEADER_SIZE + payloadSize)));
  return validateMessage(message);
}

export function startCommand(status, sequence) {
  return validateMessage({
    schema_version: SCHEMA_VERSION,
    protocol: PROTOCOL,
    kind: 'command',
    type: 'START',
    run_id: status.run_id,
    show_sha256: status.show_sha256,
    sequence,
  });
}
