import { ShowControlClient } from './show-control-client.mjs';
import { ledStatesForFrame, rgbCss, validateShowIrForViewer } from './show-led-timeline.mjs';

const ui = {
  state: document.getElementById('show-state'),
  detail: document.getElementById('show-detail'),
  start: document.getElementById('show-start'),
  droneCount: document.getElementById('drone-count'),
};

let viewer = null;
let controlClient = null;
let latestStatus = null;
let expectedDroneCount = 0;
let visibleDroneCount = 0;
let showIr = null;
let showIrSha256 = null;
let appliedShowFrameIndex = null;
let appliedLedDroneCount = 0;
let startPending = false;
let startPendingTimer = null;
const markers = new Map();
const ledStatesByDroneId = new Map();
const START_RETRY_TIMEOUT_MSEC = 3000;

function clearStartPending() {
  startPending = false;
  if (startPendingTimer !== null) window.clearTimeout(startPendingTimer);
  startPendingTimer = null;
}

function beginStartPending() {
  clearStartPending();
  startPending = true;
  startPendingTimer = window.setTimeout(() => {
    startPendingTimer = null;
    if (latestStatus?.state === 'waiting') {
      startPending = false;
      refreshStartButton();
    }
  }, START_RETRY_TIMEOUT_MSEC);
}

function setUiState(state, detail = '') {
  ui.state.dataset.state = state;
  ui.state.textContent = ({
    connecting: '接続中',
    initializing: '初期化中',
    waiting: '開始待ち',
    running: '実行中',
    completed: '完了',
    failed: 'エラー',
  })[state] ?? state;
  ui.detail.textContent = detail;
  refreshStartButton();
}

function refreshStartButton() {
  const ready = latestStatus?.state === 'waiting';
  const fleetReady = expectedDroneCount > 0 && visibleDroneCount >= expectedDroneCount;
  ui.start.disabled = !ready || !fleetReady || startPending;
  if (startPending) ui.start.textContent = '開始要求を送信済み';
  else if (!ready) ui.start.textContent = 'ドローンショー開始';
  else if (!fleetReady) ui.start.textContent = `機体表示待ち (${visibleDroneCount}/${expectedDroneCount})`;
  else ui.start.textContent = 'ドローンショー開始';
}

function resolveByBase(baseUrl, value) {
  return new URL(value, new URL(baseUrl, window.location.href)).toString();
}

function bytesToHex(bytes) {
  return [...bytes].map((value) => value.toString(16).padStart(2, '0')).join('');
}

async function loadShowIr(runtime) {
  const showConfig = runtime.show_ir;
  if (!showConfig?.url || !/^[0-9a-f]{64}$/.test(showConfig.sha256 ?? '')) {
    throw new Error('runtime Show IR configuration is invalid');
  }
  const response = await fetch(showConfig.url, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Show IR load failed: ${response.status}`);
  const encoded = await response.arrayBuffer();
  const digest = await window.crypto.subtle.digest('SHA-256', encoded);
  const actualSha256 = bytesToHex(new Uint8Array(digest));
  if (actualSha256 !== showConfig.sha256) {
    throw new Error('Show IR hash does not match runtime configuration');
  }
  const parsed = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(encoded));
  return {
    value: validateShowIrForViewer(parsed, runtime.expected_drone_count),
    sha256: actualSha256,
  };
}

function applyShowLedFrame(frameIndex) {
  if (!viewer || !showIr) return;
  if (typeof viewer.setDroneLedStates !== 'function') {
    throw new Error('Three.js Viewer does not support Drone Show LED states');
  }
  const states = ledStatesForFrame(showIr, frameIndex);
  if (frameIndex === appliedShowFrameIndex && appliedLedDroneCount >= states.length) return;
  appliedLedDroneCount = viewer.setDroneLedStates(states);
  ledStatesByDroneId.clear();
  for (const state of states) ledStatesByDroneId.set(state.droneId, state);
  for (const [droneId, marker] of markers) {
    const state = ledStatesByDroneId.get(droneId);
    if (!state) continue;
    const color = rgbCss(state.rgb);
    marker.setStyle({
      color,
      fillColor: color,
      fillOpacity: 0.2 + 0.62 * state.brightness,
    });
  }
  appliedShowFrameIndex = frameIndex;
}

async function loadViewerConfig(runtime) {
  const configUrl = new URL(
    `${runtime.threejs_root}/config/${runtime.viewer_config_name}`,
    window.location.href,
  ).toString();
  const response = await fetch(configUrl, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Viewer config load failed: ${response.status}`);
  const config = await response.json();
  const normalized = JSON.parse(JSON.stringify(config));
  normalized.three.sceneConfigPath = resolveByBase(configUrl, config.three.sceneConfigPath);
  normalized.pdu.pduDefPath = resolveByBase(configUrl, config.pdu.pduDefPath);
  return normalized;
}

function onShowStatus(status) {
  const runChanged = latestStatus?.run_id && latestStatus.run_id !== status.run_id;
  latestStatus = status;
  if (showIrSha256 && status.show_sha256 !== showIrSha256) {
    setUiState('failed', 'Show RunnerとブラウザのShow IRが一致しません');
    return;
  }
  if (Number.isSafeInteger(status.show_frame_index)) {
    try {
      applyShowLedFrame(status.show_frame_index);
    } catch (error) {
      setUiState('failed', error.message);
      return;
    }
  }
  if (runChanged || status.state !== 'waiting') clearStartPending();
  const run = status.run_id ? `run ${status.run_id.slice(0, 8)}` : '';
  if (status.state === 'failed') setUiState('failed', status.error ?? 'Show Runner failed');
  else setUiState(status.state, run);
}

function fleetMarkerSize(count) {
  if (count <= 16) return 7;
  if (count <= 64) return 5;
  if (count <= 128) return 4;
  return 3;
}

async function initialize() {
  setUiState('connecting', 'WebSocketへ自動接続しています');
  const runtimeResponse = await fetch('./runtime-config.json', { cache: 'no-store' });
  if (!runtimeResponse.ok) throw new Error('runtime-config.json could not be loaded');
  const runtime = await runtimeResponse.json();
  expectedDroneCount = runtime.expected_drone_count;
  const loadedShowIr = await loadShowIr(runtime);
  showIr = loadedShowIr.value;
  showIrSha256 = loadedShowIr.sha256;

  const [{ createDroneViewer }, { HakoniwaFrame }] = await Promise.all([
    import(`${runtime.threejs_root}/src/public/drone_viewer.js`),
    import('/src/client/src/frame.js'),
  ]);
  const config = await loadViewerConfig(runtime);
  viewer = createDroneViewer();
  viewer.configure(config);
  await viewer.initialize({ droneConfigPath: config.three.sceneConfigPath });
  viewer.setNightMode(true);
  if (runtime.led_appearance) {
    if (typeof viewer.setDroneLedAppearance !== 'function') {
      throw new Error('Three.js Viewer does not support Drone Show LED appearance');
    }
    viewer.setDroneLedAppearance(runtime.led_appearance);
  }

  let connected = false;
  while (!connected) {
    connected = await viewer.connectPdu({ wsUri: runtime.websocket_url });
    if (!connected) {
      setUiState('connecting', '接続を再試行します');
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
    }
  }
  await viewer.initDronePdu();
  const manager = viewer.withPdu((pdu) => pdu);
  if (!manager) throw new Error('Viewer PDU session is unavailable');
  controlClient = new ShowControlClient(manager, runtime, onShowStatus);
  await controlClient.start();
  setUiState('initializing', 'Show Runnerの準備を待っています');

  const originLat = Number(runtime.origin.latitude);
  const originLon = Number(runtime.origin.longitude);
  const map = L.map('map', { zoomControl: true }).setView([originLat, originLon], 17);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 20,
  }).addTo(map);

  window.setInterval(() => {
    if (!viewer) return;
    const drones = viewer.getDrones();
    visibleDroneCount = drones.filter((drone) => drone.latestPose).length;
    ui.droneCount.textContent = `${visibleDroneCount} / ${expectedDroneCount}`;
    refreshStartButton();
    const radius = fleetMarkerSize(expectedDroneCount);
    for (const drone of drones) {
      if (!drone.latestPose) continue;
      const [rosX, rosY, rosZ] = drone.latestPose.rosPos;
      const [enuX, enuY] = HakoniwaFrame.rosToEnuFrame(rosX, rosY, rosZ);
      const latLon = HakoniwaFrame.ENUToLatLon(originLat, originLon, enuX, enuY);
      const id = String(drone.droneId);
      let marker = markers.get(id);
      if (!marker) {
        const ledState = ledStatesByDroneId.get(id);
        const color = ledState ? rgbCss(ledState.rgb) : '#7dd3fc';
        marker = L.circleMarker(latLon, {
          radius,
          color,
          fillColor: color,
          fillOpacity: ledState ? 0.2 + 0.62 * ledState.brightness : 0.82,
          weight: 1,
        }).addTo(map);
        markers.set(id, marker);
      } else {
        marker.setLatLng(latLon);
      }
    }
  }, 100);

  window.addEventListener('hakoniwa-layout-changed', () => map.invalidateSize());
}

ui.start.addEventListener('click', async () => {
  if (!controlClient || ui.start.disabled) return;
  beginStartPending();
  refreshStartButton();
  try {
    await controlClient.requestStart();
  } catch (error) {
    clearStartPending();
    setUiState('failed', error.message);
  }
});

window.addEventListener('beforeunload', () => {
  clearStartPending();
  controlClient?.stop();
});
initialize().catch((error) => setUiState('failed', error.message));
