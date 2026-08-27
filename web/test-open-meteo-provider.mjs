import assert from 'node:assert/strict';
import {
  OpenMeteoProvider,
  OpenMeteoProviderError,
  meteorologicalWindToEnu,
  validateOpenMeteoResponse,
} from './open-meteo-provider.mjs';

const location = { latitude: 34.687, longitude: 135.526 };
const fixture = {
  latitude: 34.69,
  longitude: 135.53,
  elevation: 20,
  current_units: {
    time: 'unixtime', interval: 'seconds',
    wind_speed_10m: 'm/s', wind_direction_10m: '°', wind_gusts_10m: 'm/s',
  },
  current: {
    time: 1787865600, interval: 900,
    wind_speed_10m: 3, wind_direction_10m: 90, wind_gusts_10m: 5.8,
  },
};

assert.deepEqual(meteorologicalWindToEnu(3, 0), [0, -3, 0]);
assert.deepEqual(meteorologicalWindToEnu(3, 90).map((v) => Math.round(v)), [-3, 0, 0]);
assert.deepEqual(meteorologicalWindToEnu(3, 180).map((v) => Math.round(v)), [0, 3, 0]);
assert.deepEqual(meteorologicalWindToEnu(3, 270).map((v) => Math.round(v)), [3, 0, 0]);

const normalized = validateOpenMeteoResponse(fixture, {
  requestedLocation: location,
  fetchedAt: '2026-08-28T00:03:12.450Z',
});
assert.equal(normalized.wind.directionFromDeg, 90);
assert.equal(normalized.wind.directionToDeg, 270);
assert.deepEqual(normalized.wind.vectorEnuMS.map((v) => Math.round(v)), [-3, 0, 0]);

const provider = new OpenMeteoProvider({
  fetchImpl: async () => ({ ok: true, status: 200, json: async () => fixture }),
  now: () => new Date('2026-08-28T00:03:12.450Z'),
});
const url = provider.buildUrl(location);
assert.equal(url.origin + url.pathname, 'https://api.open-meteo.com/v1/forecast');
assert.equal(url.searchParams.get('wind_speed_unit'), 'ms');
assert.equal(url.searchParams.get('timeformat'), 'unixtime');
assert.equal(url.searchParams.has('models'), false);
assert.equal(url.searchParams.get('cell_selection'), 'land');
assert.deepEqual(url.searchParams.get('current').split(','), [
  'wind_speed_10m', 'wind_direction_10m', 'wind_gusts_10m',
]);
assert.equal((await provider.fetchCurrentWind(location)).wind.speedMS, 3);

assert.throws(
  () => validateOpenMeteoResponse({ ...fixture, current_units: { ...fixture.current_units, wind_speed_10m: 'km/h' } }, { requestedLocation: location }),
  (error) => error instanceof OpenMeteoProviderError && error.code === 'UNIT',
);
assert.throws(
  () => validateOpenMeteoResponse({ ...fixture, current: { ...fixture.current, wind_speed_10m: '3' } }, { requestedLocation: location }),
  (error) => error instanceof OpenMeteoProviderError && error.code === 'SCHEMA',
);

console.log('open-meteo-provider tests: ok');
