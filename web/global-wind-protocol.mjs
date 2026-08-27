export const GLOBAL_WIND_SCHEMA = 'hakoniwa.drone-show/global-wind/v1';
export const MAX_WIND_COMPONENT_M_S = 100;
export const MAX_WIND_STDDEV_M_S = 100;
export const FRAME_SIZE = 1024;
export const HEADER_SIZE = 8;
export const MAX_JSON_BYTES = FRAME_SIZE - HEADER_SIZE;
export const ROBOT_NAME = 'DroneShow';
export const COMMAND_PDU_NAME = 'global_wind_command';
export const COMMAND_CHANNEL_ID = 2;

const MAGIC = [0x48, 0x44, 0x57, 0x31]; // HDW1
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

export function normalizeDirectionFromDeg(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  return ((number % 360) + 360) % 360;
}

export function clampWindSpeedMps(value, maximum = 30) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  return Math.max(0, Math.min(maximum, number));
}

export function meteorologicalWindToRos(directionFromDeg, speedMps, verticalMps = 0) {
  const theta = normalizeDirectionFromDeg(directionFromDeg) * Math.PI / 180;
  const speed = clampWindSpeedMps(speedMps, MAX_WIND_COMPONENT_M_S);
  const vertical = Number(verticalMps);
  return [
    zeroClean(-speed * Math.cos(theta)),
    zeroClean(speed * Math.sin(theta)),
    zeroClean(Number.isFinite(vertical) ? vertical : 0),
  ];
}

export function flowDirectionToRos(directionToDeg, speedMps, verticalMps = 0) {
  const theta = normalizeDirectionFromDeg(directionToDeg) * Math.PI / 180;
  const speed = clampWindSpeedMps(speedMps, MAX_WIND_COMPONENT_M_S);
  const vertical = Number(verticalMps);
  return [
    zeroClean(speed * Math.cos(theta)),
    zeroClean(-speed * Math.sin(theta)),
    zeroClean(Number.isFinite(vertical) ? vertical : 0),
  ];
}

function zeroClean(value) {
  return Math.abs(value) < 1e-12 ? 0 : value;
}

export function createPublisherId(cryptoObject = globalThis.crypto) {
  if (typeof cryptoObject?.randomUUID === 'function') {
    return `browser-${cryptoObject.randomUUID()}`;
  }
  const random = Math.floor(Math.random() * Number.MAX_SAFE_INTEGER).toString(16);
  return `browser-${Date.now().toString(16)}-${random}`;
}

export function manualWindCommand({
  publisherId,
  sequence,
  enabled,
  directionToDeg,
  speedMps,
  speedStddevMps = 0,
  variationSeed = 1,
}) {
  if (typeof publisherId !== 'string' || publisherId.length < 1) {
    throw new Error('publisherId is required');
  }
  if (!Number.isSafeInteger(sequence) || sequence < 1) {
    throw new Error('sequence must be a positive safe integer');
  }
  const active = Boolean(enabled);
  const stddev = clampWindSpeedMps(speedStddevMps, MAX_WIND_STDDEV_M_S);
  const seed = Number(variationSeed);
  if (!Number.isSafeInteger(seed) || seed < 0) {
    throw new Error('variationSeed must be a non-negative safe integer');
  }
  return {
    schema: GLOBAL_WIND_SCHEMA,
    publisher_id: publisherId,
    sequence,
    source: { mode: 'manual', provider: null, observed_at: null },
    wind: {
      enabled: active,
      vector_ros_m_s: active
        ? flowDirectionToRos(directionToDeg, speedMps)
        : [0, 0, 0],
      variation: {
        speed_stddev_m_s: stddev,
        seed,
      },
    },
  };
}

export function physicalWindKey(command) {
  if (!command.wind.enabled) return JSON.stringify([false, [0, 0, 0]]);
  return JSON.stringify([
    true,
    command.wind.vector_ros_m_s,
    command.wind.variation.speed_stddev_m_s,
    command.wind.variation.seed,
  ]);
}

export function encodeFrame(command) {
  const payload = encoder.encode(canonicalize(command));
  if (payload.byteLength > MAX_JSON_BYTES) {
    throw new Error(`Global Wind JSON exceeds ${MAX_JSON_BYTES} bytes`);
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
    throw new Error(`Global Wind frame must contain ${FRAME_SIZE} bytes`);
  }
  if (raw.every((byte) => byte === 0)) return null;
  if (!MAGIC.every((byte, index) => raw[index] === byte)) {
    throw new Error('invalid Global Wind frame magic');
  }
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
  const payloadSize = view.getUint16(4, false);
  const flags = view.getUint16(6, false);
  if (flags !== 0 || payloadSize < 2 || payloadSize > MAX_JSON_BYTES) {
    throw new Error('invalid Global Wind frame header');
  }
  for (let index = HEADER_SIZE + payloadSize; index < raw.byteLength; index += 1) {
    if (raw[index] !== 0) throw new Error('non-zero Global Wind frame padding');
  }
  return JSON.parse(decoder.decode(raw.slice(HEADER_SIZE, HEADER_SIZE + payloadSize)));
}
