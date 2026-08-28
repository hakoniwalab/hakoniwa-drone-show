function finite(value, name) {
  const number = Number(value);
  if (!Number.isFinite(number)) throw new Error(`${name} must be finite`);
  return number;
}

export function validateWindScenarioForViewer(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Wind Scenario must be an object');
  }
  if (value.schema_version !== 1 || typeof value.scenario_id !== 'string') {
    throw new Error('Unsupported Wind Scenario');
  }
  if (!Array.isArray(value.events) || value.events.length < 1) {
    throw new Error('Wind Scenario events are missing');
  }
  let previous = -1;
  const events = value.events.map((event, index) => {
    if (!event || typeof event !== 'object' || typeof event.enabled !== 'boolean') {
      throw new Error(`Invalid Wind Scenario event ${index}`);
    }
    const timeSec = finite(event.time_sec, `events[${index}].time_sec`);
    const speedMps = finite(event.speed_m_s, `events[${index}].speed_m_s`);
    const directionToDeg = finite(
      event.direction_to_deg, `events[${index}].direction_to_deg`,
    );
    if (timeSec < 0 || timeSec <= previous || (index === 0 && timeSec !== 0)
      || speedMps < 0 || directionToDeg < 0 || directionToDeg >= 360) {
      throw new Error(`Invalid Wind Scenario event ${index}`);
    }
    previous = timeSec;
    return {
      timeSec, enabled: event.enabled, speedMps, directionToDeg,
    };
  });
  const stddev = finite(
    value.vehicle_variation?.speed_stddev_m_s,
    'vehicle_variation.speed_stddev_m_s',
  );
  if (stddev < 0) throw new Error('Wind Scenario standard deviation is invalid');
  return {
    scenarioId: value.scenario_id,
    events,
    speedStddevMps: stddev,
  };
}

export function windScenarioEventAt(scenario, showTimeUsec) {
  if (!Number.isSafeInteger(showTimeUsec) || showTimeUsec < 0) return null;
  const showTimeSec = showTimeUsec / 1_000_000;
  let activeIndex = -1;
  for (let index = 0; index < scenario.events.length; index += 1) {
    if (scenario.events[index].timeSec > showTimeSec) break;
    activeIndex = index;
  }
  if (activeIndex < 0) return null;
  return {
    index: activeIndex,
    event: scenario.events[activeIndex],
    showTimeSec,
  };
}
