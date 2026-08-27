const ENDPOINT = 'https://api.open-meteo.com/v1/forecast';
const REQUIRED_UNITS = Object.freeze({
  wind_speed_10m: 'm/s',
  wind_direction_10m: '°',
  wind_gusts_10m: 'm/s',
});

export class OpenMeteoProviderError extends Error {
  constructor(code, message, cause = undefined) {
    super(message, cause === undefined ? undefined : { cause });
    this.name = 'OpenMeteoProviderError';
    this.code = code;
  }
}

function finiteNumber(value, field) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new OpenMeteoProviderError('SCHEMA', `${field} must be a finite number`);
  }
  return value;
}

export function normalizeMeteorologicalDirection(value) {
  const direction = finiteNumber(value, 'current.wind_direction_10m');
  if (direction < 0 || direction > 360) {
    throw new OpenMeteoProviderError('RANGE', 'wind_direction_10m must be within [0, 360]');
  }
  return direction === 360 ? 0 : direction;
}

export function meteorologicalWindToEnu(speedMS, directionFromDeg) {
  const theta = directionFromDeg * Math.PI / 180;
  return [
    -speedMS * Math.sin(theta),
    -speedMS * Math.cos(theta),
    0,
  ].map((value) => (Math.abs(value) < 1e-12 ? 0 : value));
}

export function validateOpenMeteoResponse(response, {
  requestedLocation,
  fetchedAt = new Date().toISOString(),
  maxWindSpeedMS = 100,
} = {}) {
  if (response === null || typeof response !== 'object' || Array.isArray(response)) {
    throw new OpenMeteoProviderError('SCHEMA', 'response must be an object');
  }
  const current = response.current;
  const units = response.current_units;
  if (current === null || typeof current !== 'object' || Array.isArray(current)) {
    throw new OpenMeteoProviderError('SCHEMA', 'response.current must be an object');
  }
  if (units === null || typeof units !== 'object' || Array.isArray(units)) {
    throw new OpenMeteoProviderError('SCHEMA', 'response.current_units must be an object');
  }
  for (const [field, expected] of Object.entries(REQUIRED_UNITS)) {
    if (units[field] !== expected) {
      throw new OpenMeteoProviderError('UNIT', `${field} unit must be ${expected}`);
    }
  }
  const unixTime = finiteNumber(current.time, 'current.time');
  const speedMS = finiteNumber(current.wind_speed_10m, 'current.wind_speed_10m');
  const gustMS = finiteNumber(current.wind_gusts_10m, 'current.wind_gusts_10m');
  const directionFromDeg = normalizeMeteorologicalDirection(current.wind_direction_10m);
  if (speedMS < 0 || speedMS > maxWindSpeedMS || gustMS < 0 || gustMS > maxWindSpeedMS) {
    throw new OpenMeteoProviderError('RANGE', `wind speed and gust must be within [0, ${maxWindSpeedMS}]`);
  }
  const validDate = new Date(unixTime * 1000);
  if (!Number.isFinite(validDate.getTime())) {
    throw new OpenMeteoProviderError('RANGE', 'current.time is outside the supported range');
  }
  const latitude = finiteNumber(response.latitude, 'response.latitude');
  const longitude = finiteNumber(response.longitude, 'response.longitude');
  const elevation = finiteNumber(response.elevation, 'response.elevation');
  return {
    provider: 'open-meteo',
    dataType: 'forecast-model-current',
    requestedLocation: { ...requestedLocation },
    resolvedLocation: { latitude, longitude, elevationM: elevation },
    validAt: validDate.toISOString(),
    fetchedAt,
    wind: {
      speedMS,
      directionFromDeg,
      directionToDeg: (directionFromDeg + 180) % 360,
      gustMS,
      vectorEnuMS: meteorologicalWindToEnu(speedMS, directionFromDeg),
    },
  };
}

export class OpenMeteoProvider {
  constructor({
    fetchImpl = globalThis.fetch?.bind(globalThis),
    timeoutMs = 5000,
    maxWindSpeedMS = 100,
    now = () => new Date(),
  } = {}) {
    if (typeof fetchImpl !== 'function') throw new Error('fetch implementation is required');
    this.fetchImpl = fetchImpl;
    this.timeoutMs = timeoutMs;
    this.maxWindSpeedMS = maxWindSpeedMS;
    this.now = now;
    this.controller = null;
  }

  buildUrl({ latitude, longitude }) {
    const url = new URL(ENDPOINT);
    url.searchParams.set('latitude', String(latitude));
    url.searchParams.set('longitude', String(longitude));
    url.searchParams.set('current', 'wind_speed_10m,wind_direction_10m,wind_gusts_10m');
    url.searchParams.set('wind_speed_unit', 'ms');
    url.searchParams.set('timeformat', 'unixtime');
    url.searchParams.set('cell_selection', 'land');
    return url;
  }

  abort() {
    this.controller?.abort();
  }

  async fetchCurrentWind(location) {
    const url = this.buildUrl(location);
    const controller = new AbortController();
    this.controller = controller;
    const timer = globalThis.setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      let response;
      try {
        response = await this.fetchImpl(url, {
          method: 'GET', signal: controller.signal, cache: 'no-store',
        });
      } catch (error) {
        const code = error?.name === 'AbortError' ? 'TIMEOUT' : 'NETWORK';
        throw new OpenMeteoProviderError(code, code === 'TIMEOUT' ? 'Open-Meteo request timed out' : 'Open-Meteo network request failed', error);
      }
      if (!response.ok) {
        throw new OpenMeteoProviderError('HTTP', `Open-Meteo returned HTTP ${response.status}`);
      }
      let body;
      try {
        body = await response.json();
      } catch (error) {
        throw new OpenMeteoProviderError('JSON', 'Open-Meteo returned invalid JSON', error);
      }
      if (body?.error === true) {
        throw new OpenMeteoProviderError('HTTP', `Open-Meteo error: ${body.reason ?? 'unknown error'}`);
      }
      return validateOpenMeteoResponse(body, {
        requestedLocation: location,
        fetchedAt: this.now().toISOString(),
        maxWindSpeedMS: this.maxWindSpeedMS,
      });
    } finally {
      globalThis.clearTimeout(timer);
      if (this.controller === controller) this.controller = null;
    }
  }
}
