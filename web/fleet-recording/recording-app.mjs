import { createDroneViewer } from '../src/public/drone_viewer.js';
import { ShowControlClient } from './show-control-client.mjs';

const ui = {
  state: document.getElementById('state'),
  detail: document.getElementById('detail'),
  fleetCount: document.getElementById('fleet-count'),
  start: document.getElementById('show-start'),
  conditions: {
    physics: document.getElementById('condition-physics'),
    fleet: document.getElementById('condition-fleet'),
    processes: document.getElementById('condition-processes'),
    formation: document.getElementById('condition-formation'),
    clock: document.getElementById('condition-clock'),
  },
};

let viewer;
let controlClient;
let runtime;
let latestStatus;
let startPending = false;

function setState(state, detail = '') {
  ui.state.dataset.state = state;
  ui.state.textContent = ({ connecting: 'Connecting', initializing: 'Initializing', waiting: 'Waiting for START', running: 'Running', completed: 'Completed', failed: 'Error' })[state] ?? state;
  ui.detail.textContent = detail;
  refreshStartButton();
}

function visibleDroneCount() {
  return viewer?.getDrones?.().length ?? 0;
}

function refreshStartButton() {
  const visible = visibleDroneCount();
  const expected = runtime?.expected_drone_count ?? 0;
  const ready = latestStatus?.state === 'waiting';
  const fleetReady = expected > 0 && visible >= expected;
  ui.fleetCount.textContent = `Fleet visible ${visible}/${expected}`;
  ui.start.disabled = !ready || !fleetReady || startPending;
  if (startPending) ui.start.textContent = 'Start requested';
  else if (!ready) ui.start.textContent = 'Start show';
  else if (!fleetReady) ui.start.textContent = `Waiting for fleet (${visible}/${expected})`;
  else ui.start.textContent = 'Start show';
}

function resolveByBase(base, value) {
  return new URL(value, base).toString();
}

function renderConditions(conditions) {
  ui.conditions.physics.textContent = conditions.physics ?? '—';
  ui.conditions.fleet.textContent = `${conditions.drone_count ?? '—'} UAV`;
  ui.conditions.processes.textContent = `${conditions.process_count ?? '—'} × ${conditions.drones_per_process ?? '—'} UAV`;
  ui.conditions.formation.textContent = conditions.formation ?? '—';
  ui.conditions.clock.textContent = conditions.real_time_sync ? 'Real-time sync' : 'Simulation time';
}

function onStatus(status) {
  latestStatus = status;
  if (status.state !== 'waiting') startPending = false;
  setState(status.state, status.state === 'failed' ? (status.error ?? 'Show Runner failed') : `Run ${status.run_id.slice(0, 8)}`);
}

async function initialize() {
  const runtimeUrl = new URL('./runtime-config.json', import.meta.url);
  const response = await fetch(runtimeUrl, { cache: 'no-store' });
  if (!response.ok) throw new Error(`runtime configuration load failed: ${response.status}`);
  runtime = await response.json();
  renderConditions(runtime.conditions ?? {});

  const configUrl = new URL('../config/viewer-config-fleets.json', import.meta.url);
  const configResponse = await fetch(configUrl, { cache: 'no-store' });
  if (!configResponse.ok) throw new Error(`viewer configuration load failed: ${configResponse.status}`);
  const config = await configResponse.json();
  config.three.sceneConfigPath = resolveByBase(configUrl, config.three.sceneConfigPath);
  config.pdu.pduDefPath = resolveByBase(configUrl, config.pdu.pduDefPath);
  config.pdu.wsUri = runtime.websocket_url;
  config.stateInput.fleets.dynamicSpawn = true;
  config.stateInput.fleets.templateDroneIndex = 0;
  config.stateInput.fleets.maxDynamicDrones = runtime.expected_drone_count;

  viewer = createDroneViewer();
  viewer.configure(config);
  await viewer.initialize({ droneConfigPath: config.three.sceneConfigPath });
  setState('connecting', 'Connecting to WebSocket');
  if (!await viewer.connectPdu()) throw new Error('WebSocket connection failed');
  await viewer.initDronePdu();
  const manager = viewer.withPdu((pdu) => pdu);
  controlClient = new ShowControlClient(manager, runtime, onStatus);
  await controlClient.start();
  window.setInterval(refreshStartButton, 200);
  refreshStartButton();
}

ui.start.addEventListener('click', async () => {
  if (!controlClient || ui.start.disabled) return;
  startPending = true;
  refreshStartButton();
  try {
    await controlClient.requestStart();
  } catch (error) {
    startPending = false;
    setState('failed', error.message);
  }
});

initialize().catch((error) => setState('failed', error.message));
window.addEventListener('beforeunload', () => controlClient?.stop());
