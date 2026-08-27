import * as THREE from 'three';

const DEFAULT_LIGHTS = Object.freeze([
  { enabled: true, position_m: [0, -30, 8], target_m: [0, 0, 20], brightness: 1, spread_deg: 35, color: '#ffd6a0' },
  { enabled: true, position_m: [30, 0, 8], target_m: [0, 0, 20], brightness: 0.7, spread_deg: 35, color: '#ffd6a0' },
  { enabled: true, position_m: [0, 30, 8], target_m: [0, 0, 20], brightness: 0.45, spread_deg: 35, color: '#ffd6a0' },
  { enabled: true, position_m: [-30, 0, 8], target_m: [0, 0, 20], brightness: 0.7, spread_deg: 35, color: '#ffd6a0' },
]);
const BASE_LIGHT_INTENSITY = 12000;
const LIGHT_DISTANCE_M = 120;
const LIGHT_PENUMBRA = 0.55;

function finite(value, label, minimum, maximum) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < minimum || number > maximum) {
    throw new Error(`${label} must be within [${minimum}, ${maximum}]`);
  }
  return number;
}

function vector(value, fallback, label) {
  const source = value ?? fallback;
  if (!Array.isArray(source) || source.length !== 3) {
    throw new Error(`${label} must contain three numbers`);
  }
  return source.map((item, index) => finite(item, `${label}[${index}]`, -10000, 10000));
}

function color(value, fallback) {
  const normalized = String(value ?? fallback).toLowerCase();
  if (!/^#[0-9a-f]{6}$/.test(normalized)) throw new Error('light.color must be #RRGGBB');
  return normalized;
}

function normalizeLight(value, fallback, index) {
  const source = value ?? {};
  const enabled = source.enabled ?? fallback.enabled;
  if (typeof enabled !== 'boolean') throw new Error(`lights[${index}].enabled must be boolean`);
  return {
    enabled,
    position_m: vector(source.position_m, fallback.position_m, `lights[${index}].position_m`),
    target_m: vector(source.target_m, fallback.target_m, `lights[${index}].target_m`),
    brightness: finite(source.brightness ?? fallback.brightness, `lights[${index}].brightness`, 0, 5),
    spread_deg: finite(source.spread_deg ?? fallback.spread_deg, `lights[${index}].spread_deg`, 10, 70),
    color: color(source.color, fallback.color),
  };
}

export function normalizeCityLighting(value = {}) {
  const lights = value.lights ?? [];
  if (!Array.isArray(lights) || lights.length > 4) {
    throw new Error('city_lighting.lights must contain at most four lights');
  }
  return {
    enabled: value.enabled === true,
    brightness: finite(value.brightness ?? 1, 'brightness', 0, 3),
    lights: DEFAULT_LIGHTS.map((fallback, index) => normalizeLight(lights[index], fallback, index)),
  };
}

function enuToThree([east, north, up]) {
  return new THREE.Vector3(east, up, -north);
}

export function createCityLighting(initial = {}) {
  let state = normalizeCityLighting(initial);
  let selectedIndex = 0;
  const group = new THREE.Group();
  group.name = 'drone-show-city-lighting';
  const fixtures = DEFAULT_LIGHTS.map((_, index) => {
    const target = new THREE.Object3D();
    target.name = `drone-show-city-light-target-${index + 1}`;
    group.add(target);
    const light = new THREE.SpotLight();
    light.name = `drone-show-city-light-${index + 1}`;
    light.target = target;
    light.decay = 2;
    group.add(light);
    return { light, target };
  });

  const helpers = new THREE.Group();
  helpers.name = 'drone-show-city-lighting-guides';
  helpers.visible = false;
  group.add(helpers);
  const sourceMarker = new THREE.Mesh(
    new THREE.SphereGeometry(0.7, 16, 12),
    new THREE.MeshBasicMaterial({ color: 0xffd6a0, toneMapped: false }),
  );
  const targetMarker = new THREE.Mesh(
    new THREE.SphereGeometry(0.8, 16, 12),
    new THREE.MeshBasicMaterial({ color: 0x67e8f9, toneMapped: false }),
  );
  helpers.add(sourceMarker, targetMarker);
  const guideGeometry = new THREE.BufferGeometry();
  guideGeometry.setAttribute('position', new THREE.Float32BufferAttribute(new Array(6).fill(0), 3));
  const guideLine = new THREE.Line(
    guideGeometry,
    new THREE.LineBasicMaterial({ color: 0x67e8f9, transparent: true, opacity: 0.9, depthTest: false }),
  );
  guideLine.renderOrder = 1000;
  helpers.add(guideLine);

  const updateHelper = () => {
    const selected = state.lights[selectedIndex];
    sourceMarker.position.copy(enuToThree(selected.position_m));
    sourceMarker.material.color.set(selected.color);
    targetMarker.position.copy(enuToThree(selected.target_m));
    const positions = guideGeometry.getAttribute('position');
    positions.setXYZ(0, ...sourceMarker.position.toArray());
    positions.setXYZ(1, ...targetMarker.position.toArray());
    positions.needsUpdate = true;
    guideGeometry.computeBoundingSphere();
  };

  const apply = () => {
    group.visible = state.enabled;
    for (let index = 0; index < fixtures.length; index += 1) {
      const config = state.lights[index];
      const { light, target } = fixtures[index];
      light.visible = config.enabled;
      light.position.copy(enuToThree(config.position_m));
      target.position.copy(enuToThree(config.target_m));
      light.color.set(config.color);
      light.intensity = BASE_LIGHT_INTENSITY * config.brightness;
      light.distance = LIGHT_DISTANCE_M;
      light.angle = THREE.MathUtils.degToRad(config.spread_deg);
      light.penumbra = LIGHT_PENUMBRA;
    }
    updateHelper();
  };
  apply();

  return {
    object3d: group,
    getState: () => JSON.parse(JSON.stringify(state)),
    setState: (next) => {
      state = normalizeCityLighting(next);
      apply();
      return JSON.parse(JSON.stringify(state));
    },
    setSelectedIndex: (index) => {
      selectedIndex = Math.max(0, Math.min(3, Number(index) || 0));
      updateHelper();
    },
    getSelectedIndex: () => selectedIndex,
    setGuidesVisible: (visible) => {
      helpers.visible = visible === true;
    },
  };
}

function display(value) {
  const rounded = Math.abs(Number(value)) < 0.0005 ? 0 : Number(value);
  return Number(rounded.toFixed(3)).toString();
}

export function cityLightingYaml(value) {
  const state = normalizeCityLighting(value);
  const lines = [
    '  city_lighting:',
    `    enabled: ${String(state.enabled)}`,
    `    brightness: ${display(state.brightness)}`,
    '    lights:',
  ];
  for (let index = 0; index < state.lights.length; index += 1) {
    const light = state.lights[index];
    lines.push(
      `      light${index + 1}:`,
      `        enabled: ${String(light.enabled)}`,
      `        position_m: [${light.position_m.map(display).join(', ')}]`,
      `        target_m: [${light.target_m.map(display).join(', ')}]`,
      `        brightness: ${display(light.brightness)}`,
      `        spread_deg: ${display(light.spread_deg)}`,
      `        color: "${light.color}"`,
    );
  }
  return lines.join('\n');
}
