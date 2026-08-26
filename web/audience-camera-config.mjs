function finite(value, label) {
  const number = Number(value);
  if (!Number.isFinite(number)) throw new Error(`${label} must be finite`);
  return number;
}

export function normalizeAudienceCameraState(state) {
  if (!state || !Array.isArray(state.positionM) || state.positionM.length !== 3) {
    throw new Error('Audience camera state is unavailable');
  }
  return {
    positionM: state.positionM.map((value, index) => finite(value, `positionM[${index}]`)),
    yawDeg: finite(state.yawDeg, 'yawDeg'),
    pitchDeg: finite(state.pitchDeg, 'pitchDeg'),
    fovDeg: finite(state.fovDeg, 'fovDeg'),
  };
}

export function displayAudienceCameraState(state) {
  const camera = normalizeAudienceCameraState(state);
  const display = (value) => {
    const rounded = Math.abs(value) < 0.0005 ? 0 : value;
    return rounded.toFixed(2);
  };
  return {
    x: display(camera.positionM[0]),
    y: display(camera.positionM[1]),
    z: display(camera.positionM[2]),
    yaw: display(camera.yawDeg),
    pitch: display(camera.pitchDeg),
    fov: display(camera.fovDeg),
  };
}

export function audienceCameraYaml(state) {
  const value = displayAudienceCameraState(state);
  return [
    '  audience_camera:',
    `    position_m: [${value.x}, ${value.y}, ${value.z}]`,
    `    yaw_deg: ${value.yaw}`,
    `    pitch_deg: ${value.pitch}`,
    `    fov_deg: ${value.fov}`,
  ].join('\n');
}
