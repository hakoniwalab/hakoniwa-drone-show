const EARTH_RADIUS_M = 6378137.0;
const DEG2RAD = Math.PI / 180;

export function geodeticDeltaToEnu(origin, point) {
  for (const [name, value] of Object.entries({
    originLatitude: origin?.latitude,
    originLongitude: origin?.longitude,
    pointLatitude: point?.latitude,
    pointLongitude: point?.longitude,
  })) {
    if (!Number.isFinite(Number(value))) throw new TypeError(`${name} must be finite`);
  }
  const originLat = Number(origin.latitude) * DEG2RAD;
  const pointLat = Number(point.latitude) * DEG2RAD;
  const latitudeDelta = pointLat - originLat;
  const longitudeDelta = (Number(point.longitude) - Number(origin.longitude)) * DEG2RAD;
  return {
    eastM: longitudeDelta * Math.cos((originLat + pointLat) / 2) * EARTH_RADIUS_M,
    northM: latitudeDelta * EARTH_RADIUS_M,
  };
}

export function geographicEnuToShowEnu(eastM, northM, headingDeg = 0) {
  const heading = Number(headingDeg) * DEG2RAD;
  return {
    eastM: Math.cos(heading) * eastM + Math.sin(heading) * northM,
    northM: -Math.sin(heading) * eastM + Math.cos(heading) * northM,
  };
}

export function initialAudiencePosition({ venue, observer, groundHeightM, eyeHeightM }) {
  const geographic = geodeticDeltaToEnu(venue, observer);
  const local = geographicEnuToShowEnu(
    geographic.eastM,
    geographic.northM,
    venue.headingDeg ?? venue.heading_deg ?? 0,
  );
  return [local.eastM, local.northM, Number(groundHeightM) + Number(eyeHeightM)];
}

export function formatCoordinate(value, digits = 6) {
  return Number(value).toFixed(digits);
}
