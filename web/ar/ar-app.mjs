import { ShowControlClient } from '../show-control-client.mjs';
import { ledStatesForFrame, validateShowIrForViewer } from '../show-led-timeline.mjs';
import { bytesToHex, sha256Bytes } from '../sha256.mjs';
import { initialAudiencePosition } from './geo.mjs';
import {
  centroidEnuFromDroneStates,
  centroidEnuFromShowFrame,
  directionGuide,
  formatDistance,
  nearestDroneDistance,
  relativeObserverPosition,
} from './direction-guide.mjs';
import {
  applyOrientationDelta,
  orientationSample,
  requestDeviceOrientationPermission,
  smoothOrientationPose,
} from './device-orientation.mjs';

const ui = {
  cameraFeed: document.getElementById('camera-feed'),
  state: document.getElementById('ar-state'),
  permissionCard: document.getElementById('permission-card'),
  permissionDetail: document.getElementById('permission-detail'),
  arStart: document.getElementById('ar-start'),
  showStart: document.getElementById('show-start'),
  droneCount: document.getElementById('drone-count'),
  detail: document.getElementById('ar-detail'),
  directionGuide: document.getElementById('direction-guide'),
  directionArrow: document.getElementById('direction-arrow'),
  distanceToggle: document.getElementById('distance-toggle'),
  observerPosition: document.getElementById('observer-position'),
  observerHorizontal: document.getElementById('observer-horizontal'),
  observerHeight: document.getElementById('observer-height'),
  nearestDroneDistance: document.getElementById('nearest-drone-distance'),
  movementToggle: document.getElementById('movement-toggle'),
  movementControls: document.getElementById('movement-controls'),
};

let runtime;
let viewer;
let controlClient;
let cameraStream;
let showIr;
let showIrSha256;
let latestStatus;
let expectedDroneCount = 0;
let visibleDroneCount = 0;
let appliedFrameIndex = null;
let startPending = false;
let startPendingTimer = null;
let initialPositionM = null;
let initialYawDeg = null;
let orientationEnabled = false;
let orientationBaseline = null;
let orientationBasePose = null;
let latestOrientation = null;
let filteredOrientationPose = null;
let lastOrientationTimestampMs = null;
let movementEnabled = false;
let directionDistanceVisible = false;
const movementPointers = new Map();
let resolveViewerReady;
let rejectViewerReady;
const viewerReady = new Promise((resolve, reject) => {
  resolveViewerReady = resolve;
  rejectViewerReady = reject;
});
viewerReady.catch(() => {});

function setState(state, detail = '') {
  ui.state.dataset.state = state;
  ui.state.textContent = ({
    initializing: '準備中', waiting: '開始待ち', running: '実行中',
    completed: '完了', ready: 'AR表示中', connecting: '通信接続中', failed: 'エラー',
  })[state] ?? state;
  if (detail) setDetail(detail);
  refreshShowStart();
}

function setDetail(detail = '') {
  ui.detail.textContent = detail;
  ui.detail.hidden = !detail;
}

function resolveByBase(baseUrl, value) {
  return new URL(value, new URL(baseUrl, window.location.href)).toString();
}

async function loadViewerConfig() {
  const configUrl = new URL(
    `${runtime.threejs_root}/config/${runtime.viewer_config_name}`,
    window.location.href,
  ).toString();
  const response = await fetch(configUrl, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Viewer config load failed: ${response.status}`);
  const config = await response.json();
  const normalized = JSON.parse(JSON.stringify(config));
  normalized.three.sceneConfigPath = resolveByBase(configUrl, config.three.sceneConfigPath);
  normalized.three.transparentBackground = true;
  normalized.three.initialCameraMode = 'audience';
  normalized.three.audienceCamera.moveSpeedMps = runtime.ar.preview.movement_speed_m_s;
  normalized.pdu.pduDefPath = resolveByBase(configUrl, config.pdu.pduDefPath);
  normalized.pdu.wsUri = websocketUrl();
  normalized.ui = {
    ...(normalized.ui ?? {}),
    enableAttachedCameras: false,
    enableMainCameraMouseControl: false,
  };
  return normalized;
}

function websocketUrl() {
  if (window.isSecureContext && runtime.ar?.secure_websocket_url) {
    return runtime.ar.secure_websocket_url;
  }
  return runtime.websocket_url;
}

async function loadShowIr() {
  const config = runtime.show_ir;
  const runtimeConfigUrl = new URL('../runtime-config.json', window.location.href);
  const response = await fetch(new URL(config.url, runtimeConfigUrl), { cache: 'no-store' });
  if (!response.ok) throw new Error(`Show IR load failed: ${response.status}`);
  const encoded = await response.arrayBuffer();
  const digest = bytesToHex(await sha256Bytes(encoded));
  if (digest !== config.sha256) throw new Error('Show IR hash does not match runtime configuration');
  const parsed = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(encoded));
  showIrSha256 = digest;
  showIr = validateShowIrForViewer(parsed, runtime.expected_drone_count);
}

function applyLedFrame(frameIndex) {
  if (!viewer || !showIr || frameIndex === appliedFrameIndex) return;
  viewer.setDroneLedStates(ledStatesForFrame(showIr, frameIndex));
  appliedFrameIndex = frameIndex;
}

function clearStartPending() {
  startPending = false;
  if (startPendingTimer != null) window.clearTimeout(startPendingTimer);
  startPendingTimer = null;
}

function refreshShowStart() {
  const ready = latestStatus?.state === 'waiting';
  const fleetReady = expectedDroneCount > 0 && visibleDroneCount >= expectedDroneCount;
  ui.showStart.disabled = !ready || !fleetReady || startPending;
  if (!controlClient) ui.showStart.textContent = 'ショー通信を接続中';
  else if (startPending) ui.showStart.textContent = '開始要求を送信済み';
  else if (ready && !fleetReady) ui.showStart.textContent = `機体表示待ち (${visibleDroneCount}/${expectedDroneCount})`;
  else ui.showStart.textContent = 'ドローンショー開始';
}

function onShowStatus(status) {
  const runChanged = latestStatus?.run_id && latestStatus.run_id !== status.run_id;
  latestStatus = status;
  if (showIrSha256 && status.show_sha256 !== showIrSha256) {
    setState('failed', 'Show RunnerとARブラウザのShow IRが一致しません');
    return;
  }
  if (Number.isSafeInteger(status.show_frame_index)) applyLedFrame(status.show_frame_index);
  if (runChanged || status.state !== 'waiting') clearStartPending();
  setState(status.state, status.state === 'failed' ? status.error : '');
}

function setObserverLocation(observer, source, accuracyM = null) {
  const config = runtime.ar;
  initialPositionM = initialAudiencePosition({
    venue: {
      ...config.venue,
      headingDeg: config.venue.heading_deg,
    },
    observer,
    groundHeightM: config.ground_height_m,
    eyeHeightM: config.preview.eye_height_m,
  });
  viewer.setAudienceCameraPose({ positionM: initialPositionM });
  initialYawDeg = viewer.getAudienceCameraState().yawDeg;
  const accuracy = accuracyM == null ? '' : `（GPS ±${Math.round(accuracyM)} m）`;
  setDetail(`${source}を初期位置に設定しました${accuracy}`);
}

function getCurrentPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('このブラウザでは現在地を取得できません'));
      return;
    }
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: true,
      timeout: 12000,
      maximumAge: 0,
    });
  });
}

async function useDeviceLocation() {
  setDetail('現在地を一度だけ取得しています');
  const position = await getCurrentPosition();
  setObserverLocation(
    { latitude: position.coords.latitude, longitude: position.coords.longitude },
    '現在地',
    position.coords.accuracy,
  );
}

function usePreviewLocation() {
  const override = runtime.ar.preview.override;
  if (!override) throw new Error('テスト位置が設定されていません');
  setObserverLocation(override, 'テスト位置');
}

async function startCamera() {
  if (!window.isSecureContext && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
    throw new Error('iPhoneのカメラARにはHTTPS接続が必要です');
  }
  if (!navigator.mediaDevices?.getUserMedia) throw new Error('このブラウザではカメラを利用できません');
  cameraStream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: 'environment' } },
    audio: false,
  });
  ui.cameraFeed.srcObject = cameraStream;
  await ui.cameraFeed.play();
}

function onDeviceOrientation(event) {
  const sample = orientationSample(event);
  if (!sample) return;
  latestOrientation = sample;
  if (!orientationEnabled) return;
  if (!orientationBaseline) orientationBaseline = sample;
  if (!orientationBasePose) orientationBasePose = viewer.getAudienceCameraState();
  const desiredPose = applyOrientationDelta(
    orientationBasePose,
    orientationBaseline,
    sample,
  );
  const camera = viewer.getAudienceCameraState();
  const target = directionTarget();
  const targetDistanceM = target
    ? Math.hypot(
      target[0] - camera.positionM[0],
      target[1] - camera.positionM[1],
      target[2] - camera.positionM[2],
    )
    : 0;
  const timestampMs = Number(event.timeStamp) || performance.now();
  const elapsedSec = lastOrientationTimestampMs == null
    ? 1 / 60
    : (timestampMs - lastOrientationTimestampMs) / 1000;
  filteredOrientationPose = smoothOrientationPose(
    filteredOrientationPose,
    desiredPose,
    targetDistanceM,
    elapsedSec,
  );
  lastOrientationTimestampMs = timestampMs;
  viewer.setAudienceCameraPose(filteredOrientationPose);
}

function applyMovementInput() {
  const actions = new Set(movementPointers.values());
  for (const button of ui.movementControls.querySelectorAll('button')) {
    button.dataset.active = String(actions.has(button.dataset.cameraMove));
  }
  viewer?.setAudienceCameraMovementInput({
    forward: Number(actions.has('forward')) - Number(actions.has('backward')),
    right: Number(actions.has('right')) - Number(actions.has('left')),
    up: Number(actions.has('up')) - Number(actions.has('down')),
  });
}

function setMovementEnabled(enabled) {
  movementEnabled = !!enabled;
  ui.movementToggle.setAttribute('aria-pressed', String(movementEnabled));
  ui.movementToggle.textContent = movementEnabled ? '閉じる' : '移動';
  ui.movementToggle.setAttribute(
    'aria-label',
    movementEnabled ? '仮想移動を閉じる' : '仮想移動を開く',
  );
  ui.movementControls.hidden = !movementEnabled;
  if (!movementEnabled) {
    movementPointers.clear();
    applyMovementInput();
  }
}

async function setOrientationEnabled(enabled, { requestPermission = true } = {}) {
  if (enabled) {
    if (requestPermission) await requestDeviceOrientationPermission();
    orientationBasePose = viewer.getAudienceCameraState();
    orientationBaseline = latestOrientation;
    filteredOrientationPose = {
      yawDeg: orientationBasePose.yawDeg,
      pitchDeg: orientationBasePose.pitchDeg,
    };
    lastOrientationTimestampMs = null;
    orientationEnabled = true;
    window.addEventListener('deviceorientation', onDeviceOrientation, true);
  } else {
    orientationEnabled = false;
    window.removeEventListener('deviceorientation', onDeviceOrientation, true);
    orientationBaseline = null;
    orientationBasePose = null;
    filteredOrientationPose = null;
    lastOrientationTimestampMs = null;
  }
}

function directionTarget() {
  const liveCenter = centroidEnuFromDroneStates(viewer?.getDroneStates() ?? []);
  if (liveCenter) return liveCenter;
  return centroidEnuFromShowFrame(showIr, latestStatus?.show_frame_index ?? 0);
}

function updateDirectionGuide() {
  const camera = viewer?.getAudienceCameraState();
  const target = directionTarget();
  if (!camera?.enabled || !target || ui.permissionCard.hidden !== true) {
    ui.directionGuide.hidden = true;
    ui.distanceToggle.hidden = true;
    ui.observerPosition.hidden = true;
    window.requestAnimationFrame(updateDirectionGuide);
    return;
  }
  const guide = directionGuide({
    observerPositionM: camera.positionM,
    targetPositionM: target,
    yawDeg: camera.yawDeg,
    pitchDeg: camera.pitchDeg,
    fovDeg: camera.fovDeg,
    viewportWidth: window.innerWidth,
    viewportHeight: window.innerHeight,
  });
  ui.directionGuide.hidden = guide.inView;
  ui.directionGuide.style.left = `${guide.leftPx}px`;
  ui.directionGuide.style.top = `${guide.topPx}px`;
  ui.directionArrow.style.transform = `rotate(${guide.rotationDeg}deg)`;
  ui.distanceToggle.hidden = false;
  ui.distanceToggle.textContent = directionDistanceVisible
    ? `距離 ${formatDistance(guide.distanceM)}`
    : '距離';
  ui.distanceToggle.setAttribute(
    'aria-label',
    directionDistanceVisible
      ? 'ドローンまでの距離を非表示'
      : 'ドローンまでの距離を表示',
  );
  if (initialPositionM && initialYawDeg != null) {
    const relative = relativeObserverPosition({
      positionM: camera.positionM,
      initialPositionM,
      initialYawDeg,
      groundHeightM: runtime.ar.ground_height_m,
    });
    const signed = (value) => `${value >= 0 ? '+' : ''}${value.toFixed(1)}`;
    ui.observerHorizontal.textContent = `前 ${signed(relative.forwardM)} m ／ 右 ${signed(relative.rightM)} m`;
    ui.observerHeight.textContent = `地面から ${Math.max(0, relative.heightM).toFixed(1)} m`;
    const nearest = nearestDroneDistance(camera.positionM, viewer.getDroneStates());
    ui.nearestDroneDistance.textContent = nearest == null
      ? '最寄り機 --'
      : `最寄り機 ${formatDistance(nearest)}`;
    ui.observerPosition.hidden = false;
  }
  window.requestAnimationFrame(updateDirectionGuide);
}

async function initializeRuntime() {
  const response = await fetch('../runtime-config.json', { cache: 'no-store' });
  if (!response.ok) throw new Error('runtime-config.json could not be loaded');
  runtime = await response.json();
  if (runtime.ar?.enabled !== true) throw new Error('ARはこの構成で有効になっていません');
  ui.arStart.disabled = false;
  ui.permissionDetail.textContent = 'カメラARを開始できます';
  expectedDroneCount = runtime.expected_drone_count;
  await loadShowIr();
  const { createDroneViewer } = await import(`${runtime.threejs_root}/src/public/drone_viewer.js`);
  const config = await loadViewerConfig();
  viewer = createDroneViewer();
  viewer.configure(config);
  await viewer.initialize({ droneConfigPath: config.three.sceneConfigPath });
  viewer.setAudienceCameraEnabled(true);
  viewer.setNightMode(true);
  viewer.setDroneLedAppearance(runtime.led_appearance);
  resolveViewerReady();
  window.requestAnimationFrame(updateDirectionGuide);
  setState('connecting');
  let connected = false;
  let connectionAttempt = 0;
  while (!connected) {
    connectionAttempt += 1;
    connected = await viewer.connectPdu({ wsUri: websocketUrl() });
    if (!connected) {
      setState(
        'connecting',
        `ショー通信を接続中（再試行 ${connectionAttempt}）`,
      );
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
    }
  }
  await viewer.initDronePdu();
  const manager = viewer.withPdu((pdu) => pdu);
  controlClient = new ShowControlClient(manager, runtime, onShowStatus);
  await controlClient.start();
  window.setInterval(() => {
    visibleDroneCount = viewer.getDrones().filter((drone) => drone.latestPose).length;
    ui.droneCount.textContent = `${visibleDroneCount} / ${expectedDroneCount}`;
    refreshShowStart();
  }, 100);
  if (!ui.permissionCard.hidden) ui.permissionDetail.textContent = '準備できました';
}

ui.arStart.addEventListener('click', async () => {
  if (!runtime) {
    ui.permissionDetail.textContent = 'AR設定の読込完了を待っています';
    return;
  }
  ui.arStart.disabled = true;
  ui.permissionDetail.textContent = 'ARを準備しています';
  try {
    let orientationWarning = '';
    let orientationPermissionGranted = false;
    if (runtime.ar.preview.device_orientation === 'optional') {
      try {
        await requestDeviceOrientationPermission();
        orientationPermissionGranted = true;
      } catch (error) {
        orientationWarning = `端末姿勢は使用せず表示します: ${error.message}`;
      }
    }
    await startCamera();
    ui.permissionCard.hidden = true;
    ui.showStart.hidden = false;
    ui.movementToggle.hidden = false;
    setState('initializing', '3D Viewerを準備しています');
    ui.permissionDetail.textContent = '3D Viewerを準備しています';
    await viewerReady;
    if (orientationPermissionGranted) {
      await setOrientationEnabled(true, { requestPermission: false });
    }
    if (runtime.ar.preview.location_source === 'device') {
      try {
        await useDeviceLocation();
      } catch (error) {
        if (!runtime.ar.preview.override) throw error;
        usePreviewLocation();
        setDetail(`現在地を取得できないためテスト位置を使用: ${error.message}`);
      }
    } else {
      usePreviewLocation();
    }
    if (orientationWarning) setDetail(orientationWarning);
    setState(latestStatus?.state ?? (controlClient ? 'ready' : 'connecting'));
  } catch (error) {
    cameraStream?.getTracks().forEach((track) => track.stop());
    cameraStream = null;
    ui.arStart.disabled = false;
    ui.permissionDetail.textContent = error.message;
    setState('failed', error.message);
  }
});

ui.showStart.addEventListener('click', async () => {
  if (!controlClient || ui.showStart.disabled) return;
  startPending = true;
  refreshShowStart();
  startPendingTimer = window.setTimeout(() => {
    if (latestStatus?.state === 'waiting') {
      startPending = false;
      refreshShowStart();
    }
  }, 3000);
  try {
    await controlClient.requestStart();
  } catch (error) {
    clearStartPending();
    setState('failed', error.message);
  }
});
ui.movementToggle.addEventListener('click', () => setMovementEnabled(!movementEnabled));
ui.distanceToggle.addEventListener('click', () => {
  directionDistanceVisible = !directionDistanceVisible;
  ui.distanceToggle.setAttribute('aria-pressed', String(directionDistanceVisible));
});
for (const button of ui.movementControls.querySelectorAll('[data-camera-move]')) {
  const release = (event) => {
    movementPointers.delete(event.pointerId);
    button.releasePointerCapture?.(event.pointerId);
    applyMovementInput();
  };
  button.addEventListener('pointerdown', (event) => {
    if (!movementEnabled || !viewer) return;
    event.preventDefault();
    movementPointers.set(event.pointerId, button.dataset.cameraMove);
    button.setPointerCapture?.(event.pointerId);
    applyMovementInput();
  });
  button.addEventListener('pointerup', release);
  button.addEventListener('pointercancel', release);
  button.addEventListener('lostpointercapture', release);
}
window.addEventListener('beforeunload', () => {
  cameraStream?.getTracks().forEach((track) => track.stop());
  controlClient?.stop();
});
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) return;
  movementPointers.clear();
  applyMovementInput();
});

initializeRuntime().catch((error) => {
  rejectViewerReady(error);
  ui.arStart.disabled = true;
  ui.permissionDetail.textContent = error.message;
  setState('failed');
});
