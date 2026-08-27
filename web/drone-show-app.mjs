import { ShowControlClient } from './show-control-client.mjs';
import { audienceCameraYaml, displayAudienceCameraState } from './audience-camera-config.mjs';
import { ledStatesForFrame, rgbCss, validateShowIrForViewer } from './show-led-timeline.mjs';
import { bytesToHex, sha256Bytes } from './sha256.mjs';
import { createAudienceCrowd } from './audience-crowd.mjs';
import { cityLightingYaml, createCityLighting, normalizeCityLighting } from './city-lighting.mjs';

const ui = {
  state: document.getElementById('show-state'),
  detail: document.getElementById('show-detail'),
  start: document.getElementById('show-start'),
  droneCount: document.getElementById('drone-count'),
  cameraAudience: document.getElementById('camera-audience'),
  cameraFree: document.getElementById('camera-free'),
  cameraMovementToggle: document.getElementById('camera-movement-toggle'),
  cameraMovementControls: document.getElementById('camera-movement-controls'),
  cameraHelp: document.getElementById('camera-help'),
  cameraState: document.getElementById('camera-state'),
  cameraX: document.getElementById('camera-x'),
  cameraY: document.getElementById('camera-y'),
  cameraZ: document.getElementById('camera-z'),
  cameraYaw: document.getElementById('camera-yaw'),
  cameraPitch: document.getElementById('camera-pitch'),
  cameraFov: document.getElementById('camera-fov'),
  cameraCopy: document.getElementById('camera-copy'),
  cameraCopyStatus: document.getElementById('camera-copy-status'),
  cityLightingPanel: document.getElementById('city-lighting-panel'),
  lightingCityBrightness: document.getElementById('lighting-city-brightness'),
  lightingCityValue: document.getElementById('lighting-city-value'),
  lightingSelect: document.getElementById('lighting-select'),
  lightingEnabled: document.getElementById('lighting-enabled'),
  lightingLightBrightness: document.getElementById('lighting-light-brightness'),
  lightingLightValue: document.getElementById('lighting-light-value'),
  lightingSpread: document.getElementById('lighting-spread'),
  lightingSpreadValue: document.getElementById('lighting-spread-value'),
  lightingColor: document.getElementById('lighting-color'),
  lightingMoveStep: document.getElementById('lighting-move-step'),
  lightingTargetValue: document.getElementById('lighting-target-value'),
  lightingEditSource: document.getElementById('lighting-edit-source'),
  lightingEditTarget: document.getElementById('lighting-edit-target'),
  lightingCopy: document.getElementById('lighting-copy'),
  lightingCopyStatus: document.getElementById('lighting-copy-status'),
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
let cameraCopyStatusTimer = null;
let lightingCopyStatusTimer = null;
let cityLightingController = null;
let cityLightingMapContext = null;
let cityLightingMapMarker = null;
let cityLightingEditMode = 'target';
let audienceCameraEnabled = false;
let cameraMovementEnabled = false;
const cameraMovementPointers = new Map();

function setCityLightingInputs(state) {
  const selectedIndex = Number(ui.lightingSelect.value) || 0;
  const light = state.lights[selectedIndex];
  ui.lightingCityBrightness.value = state.brightness;
  ui.lightingEnabled.checked = light.enabled;
  ui.lightingLightBrightness.value = light.brightness;
  ui.lightingSpread.value = light.spread_deg;
  ui.lightingColor.value = light.color;
  refreshCityLightingDisplay(state);
}

function cityLightingFromInputs() {
  const current = cityLightingController.getState();
  const selectedIndex = Number(ui.lightingSelect.value) || 0;
  const lights = current.lights.map((light) => ({ ...light }));
  lights[selectedIndex] = {
    ...lights[selectedIndex],
    enabled: ui.lightingEnabled.checked,
    brightness: ui.lightingLightBrightness.value,
    spread_deg: ui.lightingSpread.value,
    color: ui.lightingColor.value,
  };
  return normalizeCityLighting({
    ...current,
    brightness: ui.lightingCityBrightness.value,
    lights,
  });
}

function nightLightingForBrightness(brightness) {
  return {
    ambientIntensity: 0.18 + 0.10 * brightness,
    directionalIntensity: 0.38 + 0.10 * brightness,
    hemisphereIntensity: 0.22 + 0.04 * brightness,
    exposure: 0.72 + 0.16 * brightness,
  };
}

function refreshCityLightingDisplay(state) {
  const selectedIndex = Number(ui.lightingSelect.value) || 0;
  const light = state.lights[selectedIndex];
  ui.lightingCityValue.textContent = `${Math.round(state.brightness * 100)}%`;
  ui.lightingLightValue.textContent = `${Math.round(light.brightness * 100)}%`;
  ui.lightingSpreadValue.textContent = `${Math.round(light.spread_deg)}°`;
  const edited = cityLightingEditMode === 'source' ? light.position_m : light.target_m;
  const [east, north, up] = edited;
  const label = cityLightingEditMode === 'source' ? '光源' : '照射先';
  ui.lightingTargetValue.textContent = `${label} E ${east.toFixed(1)} / N ${north.toFixed(1)} / 高さ ${up.toFixed(1)} m`;
  if (cityLightingMapContext && ui.cityLightingPanel.open) {
    const { map, frame, originLat, originLon } = cityLightingMapContext;
    const latLon = frame.ENUToLatLon(originLat, originLon, east, north);
    if (!cityLightingMapMarker) {
      cityLightingMapMarker = L.circleMarker(latLon, {
        radius: 8, color: '#67e8f9', fillColor: '#ffd6a0', fillOpacity: 0.9, weight: 2,
      }).addTo(map).bindTooltip(label);
    } else {
      cityLightingMapMarker.setLatLng(latLon);
      cityLightingMapMarker.setTooltipContent(label);
    }
  }
}

function applyCityLightingInputs() {
  if (!viewer || !cityLightingController) return;
  try {
    const state = cityLightingFromInputs();
    cityLightingController.setState(state);
    viewer.setNightLighting(nightLightingForBrightness(state.brightness));
    refreshCityLightingDisplay(state);
    ui.lightingCopyStatus.textContent = '';
  } catch (error) {
    ui.lightingCopyStatus.textContent = error.message;
    ui.lightingCopyStatus.dataset.failed = 'true';
  }
}

function setCityLightingEditMode(mode) {
  cityLightingEditMode = mode === 'source' ? 'source' : 'target';
  ui.lightingEditSource.setAttribute('aria-pressed', String(cityLightingEditMode === 'source'));
  ui.lightingEditTarget.setAttribute('aria-pressed', String(cityLightingEditMode === 'target'));
  if (cityLightingController) refreshCityLightingDisplay(cityLightingController.getState());
}

function applyCameraMovementInput() {
  const actions = new Set(cameraMovementPointers.values());
  for (const button of ui.cameraMovementControls.querySelectorAll('button')) {
    button.dataset.active = String(actions.has(button.dataset.cameraMove));
  }
  viewer?.setAudienceCameraMovementInput?.({
    forward: Number(actions.has('forward')) - Number(actions.has('backward')),
    right: Number(actions.has('right')) - Number(actions.has('left')),
    up: Number(actions.has('up')) - Number(actions.has('down')),
  });
}

function clearCameraMovementInput() {
  cameraMovementPointers.clear();
  applyCameraMovementInput();
}

function setCameraMovementEnabled(enabled) {
  cameraMovementEnabled = !!enabled && audienceCameraEnabled;
  ui.cameraMovementToggle.setAttribute('aria-pressed', String(cameraMovementEnabled));
  ui.cameraMovementToggle.textContent = cameraMovementEnabled ? '移動操作 ON' : '移動操作 OFF';
  ui.cameraMovementControls.hidden = !cameraMovementEnabled;
  if (!cameraMovementEnabled) clearCameraMovementInput();
}

function refreshAudienceCameraState() {
  const state = viewer?.getAudienceCameraState?.();
  const visible = state?.enabled === true;
  ui.cameraState.hidden = !visible;
  if (!visible) return null;
  const display = displayAudienceCameraState(state);
  ui.cameraX.textContent = display.x;
  ui.cameraY.textContent = display.y;
  ui.cameraZ.textContent = display.z;
  ui.cameraYaw.textContent = display.yaw;
  ui.cameraPitch.textContent = display.pitch;
  ui.cameraFov.textContent = display.fov;
  return state;
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand('copy');
  textarea.remove();
  if (!copied) throw new Error('clipboard is unavailable');
}

function showCameraCopyStatus(message, failed = false) {
  if (cameraCopyStatusTimer !== null) window.clearTimeout(cameraCopyStatusTimer);
  ui.cameraCopyStatus.textContent = message;
  ui.cameraCopyStatus.dataset.failed = String(failed);
  cameraCopyStatusTimer = window.setTimeout(() => {
    ui.cameraCopyStatus.textContent = '';
    cameraCopyStatusTimer = null;
  }, 2500);
}

function showLightingCopyStatus(message, failed = false) {
  if (lightingCopyStatusTimer !== null) window.clearTimeout(lightingCopyStatusTimer);
  ui.lightingCopyStatus.textContent = message;
  ui.lightingCopyStatus.dataset.failed = String(failed);
  lightingCopyStatusTimer = window.setTimeout(() => {
    ui.lightingCopyStatus.textContent = '';
    lightingCopyStatusTimer = null;
  }, 2500);
}

function setCameraMode(mode) {
  if (!viewer) return false;
  const audience = mode === 'audience';
  const changed = viewer.setAudienceCameraEnabled?.(audience) ?? false;
  if (!changed && audience) return false;
  ui.cameraAudience.setAttribute('aria-pressed', String(audience));
  ui.cameraFree.setAttribute('aria-pressed', String(!audience));
  audienceCameraEnabled = audience;
  ui.cameraMovementToggle.hidden = !audience;
  if (!audience) setCameraMovementEnabled(false);
  ui.cameraHelp.hidden = !audience;
  refreshAudienceCameraState();
  return true;
}

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

async function loadShowIr(runtime) {
  const showConfig = runtime.show_ir;
  if (!showConfig?.url || !/^[0-9a-f]{64}$/.test(showConfig.sha256 ?? '')) {
    throw new Error('runtime Show IR configuration is invalid');
  }
  const response = await fetch(showConfig.url, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Show IR load failed: ${response.status}`);
  const encoded = await response.arrayBuffer();
  const actualSha256 = bytesToHex(await sha256Bytes(encoded));
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
  const audienceAvailable = runtime.camera?.audience_available === true;
  ui.cameraAudience.disabled = !audienceAvailable;
  ui.cameraFree.disabled = false;
  setCameraMode(
    audienceAvailable && runtime.camera?.initial_mode === 'audience'
      ? 'audience'
      : 'free',
  );
  const crowd = createAudienceCrowd(runtime.crowd, viewer.getAudienceCameraState?.());
  if (crowd) viewer.addSceneDecoration(crowd);
  viewer.setNightMode(true);
  const cityLighting = normalizeCityLighting(runtime.city_lighting);
  if (cityLighting.enabled) {
    if (typeof viewer.setNightLighting !== 'function') {
      throw new Error('Three.js Viewer does not support runtime city lighting');
    }
    cityLightingController = createCityLighting(cityLighting);
    viewer.addSceneDecoration(cityLightingController.object3d);
    viewer.setNightLighting(nightLightingForBrightness(cityLighting.brightness));
    setCityLightingInputs(cityLighting);
    ui.cityLightingPanel.hidden = false;
  }
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
  if (cityLightingController) {
    cityLightingMapContext = { map, frame: HakoniwaFrame, originLat, originLon };
    refreshCityLightingDisplay(cityLightingController.getState());
    map.on('click', (event) => {
      if (!ui.cityLightingPanel.open) return;
      const [east, north] = HakoniwaFrame.latlonToENU(
        originLat, originLon, event.latlng.lat, event.latlng.lng,
      );
      const state = cityLightingController.getState();
      const selectedIndex = cityLightingController.getSelectedIndex();
      const position = cityLightingEditMode === 'source'
        ? state.lights[selectedIndex].position_m
        : state.lights[selectedIndex].target_m;
      position[0] = east;
      position[1] = north;
      cityLightingController.setState(state);
      setCityLightingInputs(state);
      applyCityLightingInputs();
    });
  }

  window.setInterval(() => {
    if (!viewer) return;
    refreshAudienceCameraState();
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

ui.cameraAudience.addEventListener('click', () => setCameraMode('audience'));
ui.cameraFree.addEventListener('click', () => setCameraMode('free'));
ui.cameraMovementToggle.addEventListener('click', () => {
  setCameraMovementEnabled(!cameraMovementEnabled);
});
for (const button of ui.cameraMovementControls.querySelectorAll('[data-camera-move]')) {
  const release = (event) => {
    if (!cameraMovementPointers.has(event.pointerId)) return;
    cameraMovementPointers.delete(event.pointerId);
    button.releasePointerCapture?.(event.pointerId);
    applyCameraMovementInput();
  };
  button.addEventListener('pointerdown', (event) => {
    if (!cameraMovementEnabled) return;
    event.preventDefault();
    cameraMovementPointers.set(event.pointerId, button.dataset.cameraMove);
    button.dataset.active = 'true';
    button.setPointerCapture?.(event.pointerId);
    applyCameraMovementInput();
  });
  button.addEventListener('pointerup', release);
  button.addEventListener('pointercancel', release);
  button.addEventListener('lostpointercapture', release);
}
window.addEventListener('blur', clearCameraMovementInput);
document.addEventListener('visibilitychange', () => {
  if (document.hidden) clearCameraMovementInput();
});
ui.cameraCopy.addEventListener('click', async () => {
  const state = refreshAudienceCameraState();
  if (!state) return;
  try {
    await copyText(audienceCameraYaml(state));
    showCameraCopyStatus('コピーしました');
  } catch (error) {
    showCameraCopyStatus(`コピー失敗: ${error.message}`, true);
  }
});
for (const input of ui.cityLightingPanel.querySelectorAll('input')) {
  input.addEventListener('input', applyCityLightingInputs);
  input.addEventListener('change', applyCityLightingInputs);
}
ui.lightingSelect.addEventListener('change', () => {
  if (!cityLightingController) return;
  cityLightingController.setSelectedIndex(Number(ui.lightingSelect.value));
  setCityLightingInputs(cityLightingController.getState());
});
ui.lightingEditSource.addEventListener('click', () => setCityLightingEditMode('source'));
ui.lightingEditTarget.addEventListener('click', () => setCityLightingEditMode('target'));
ui.cityLightingPanel.addEventListener('toggle', () => {
  cityLightingController?.setGuidesVisible(ui.cityLightingPanel.open);
  if (ui.cityLightingPanel.open && cityLightingController) {
    refreshCityLightingDisplay(cityLightingController.getState());
  } else if (cityLightingMapMarker && cityLightingMapContext) {
    cityLightingMapContext.map.removeLayer(cityLightingMapMarker);
    cityLightingMapMarker = null;
  }
});
for (const button of ui.cityLightingPanel.querySelectorAll('[data-lighting-move]')) {
  button.addEventListener('click', () => {
    if (!cityLightingController) return;
    const step = Number(ui.lightingMoveStep.value) || 1;
    const state = cityLightingController.getState();
    const selectedIndex = cityLightingController.getSelectedIndex();
    const target = cityLightingEditMode === 'source'
      ? state.lights[selectedIndex].position_m
      : state.lights[selectedIndex].target_m;
    const movement = button.dataset.lightingMove;
    if (movement === 'east') target[0] += step;
    if (movement === 'west') target[0] -= step;
    if (movement === 'north') target[1] += step;
    if (movement === 'south') target[1] -= step;
    if (movement === 'up') target[2] += step;
    if (movement === 'down') target[2] -= step;
    cityLightingController.setState(state);
    setCityLightingInputs(state);
    applyCityLightingInputs();
  });
}
ui.lightingCopy.addEventListener('click', async () => {
  if (!cityLightingController) return;
  try {
    const state = cityLightingFromInputs();
    await copyText(cityLightingYaml(state));
    showLightingCopyStatus('コピーしました');
  } catch (error) {
    showLightingCopyStatus(`コピー失敗: ${error.message}`, true);
  }
});

window.addEventListener('beforeunload', () => {
  clearCameraMovementInput();
  clearStartPending();
  if (cameraCopyStatusTimer !== null) window.clearTimeout(cameraCopyStatusTimer);
  if (lightingCopyStatusTimer !== null) window.clearTimeout(lightingCopyStatusTimer);
  controlClient?.stop();
});
initialize().catch((error) => setUiState('failed', error.message));
