export function validateShowIrForViewer(value, expectedDroneCount) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Show IR must be an object');
  }
  if (!Array.isArray(value.drone_ids) || value.drone_ids.length !== expectedDroneCount) {
    throw new Error('Show IR drone count does not match runtime');
  }
  if (!Array.isArray(value.timeline) || value.timeline.length < 1) {
    throw new Error('Show IR timeline is empty');
  }
  const expectedIds = value.drone_ids.map(String);
  for (const [frameIndex, frame] of value.timeline.entries()) {
    if (!Array.isArray(frame.states) || frame.states.length !== expectedIds.length) {
      throw new Error(`Show IR frame ${frameIndex} has an invalid state count`);
    }
    for (const [stateIndex, state] of frame.states.entries()) {
      const led = state?.led;
      if (String(state?.drone_id ?? '') !== expectedIds[stateIndex]
        || !Array.isArray(led?.rgb) || led.rgb.length !== 3
        || led.rgb.some((component) => !Number.isInteger(component)
          || component < 0 || component > 255)
        || !Number.isFinite(led?.brightness)
        || led.brightness < 0 || led.brightness > 1) {
        throw new Error(`Show IR frame ${frameIndex} has an invalid LED state`);
      }
    }
  }
  return value;
}

export function ledStatesForFrame(showIr, frameIndex) {
  if (!Number.isSafeInteger(frameIndex)
    || frameIndex < 0 || frameIndex >= showIr.timeline.length) {
    throw new Error(`Show IR frame index is out of range: ${frameIndex}`);
  }
  return showIr.timeline[frameIndex].states.map((state) => ({
    droneId: String(state.drone_id),
    rgb: [...state.led.rgb],
    brightness: Number(state.led.brightness),
  }));
}

export function rgbCss(rgb) {
  return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}
