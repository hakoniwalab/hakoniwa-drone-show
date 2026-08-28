import assert from 'node:assert/strict';
import {
  validateWindScenarioForViewer,
  windScenarioEventAt,
} from './wind-scenario-view.mjs';

const scenario = validateWindScenarioForViewer({
  schema_version: 1,
  scenario_id: 'test-gust',
  seed: 1,
  events: [
    { time_sec: 0, enabled: true, speed_m_s: 0, direction_to_deg: 90 },
    { time_sec: 15, enabled: true, speed_m_s: 4, direction_to_deg: 90 },
    { time_sec: 30, enabled: true, speed_m_s: 8, direction_to_deg: 120 },
  ],
  vehicle_variation: { type: 'fixed_gain', speed_stddev_m_s: 0.32 },
});

assert.equal(windScenarioEventAt(scenario, 14_999_999).index, 0);
assert.equal(windScenarioEventAt(scenario, 15_000_000).index, 1);
assert.equal(windScenarioEventAt(scenario, 30_250_000).event.speedMps, 8);
assert.equal(windScenarioEventAt(scenario, null), null);

console.log('wind-scenario-view: ok');
