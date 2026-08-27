# Open-Meteo Live Wind Provider Specification

Status: Draft for implementation  
Target repository: `hakoniwalab/hakoniwa-drone-show`  
Target feature: `Global Wind for Virtual Drone Show / WND-3 Live weather`  
Primary provider: Open-Meteo Forecast API  
Primary purpose: PLATEAU AWARD demonstration and non-commercial evaluation

---

## 1. Purpose

This document fixes the external service contract and the implementation rules for the
`Live weather` input mode of Global Wind.

The objective is deliberately narrow:

> Resolve the PLATEAU venue latitude/longitude, fetch the latest model-derived wind from
> Open-Meteo, normalize it into the same Global Wind command used by Manual mode, and apply
> it to all drones through the existing Global Wind Asset.

This provider MUST NOT know how individual Drone `Disturbance` PDUs are written.

The intended data flow is:

```text
PLATEAU venue
    │
    │ latitude / longitude
    ▼
Open-Meteo Provider Adapter
    │
    │ normalized live-wind state
    ▼
Global Wind Producer
    │
    │ Global Wind JSON v1
    ▼
Web PDU Bridge
    │
    ▼
Global Wind Command PDU
    │
    ▼
Global Wind Asset
    │
    ├─ Drone-1 disturb
    ├─ Drone-2 disturb
    └─ Drone-N disturb
```

The provider adapter is therefore an **input adapter**, not a simulation asset.

---

## 2. Scope

### 2.1 In scope

The first Open-Meteo implementation SHALL:

- fetch wind data for one venue latitude/longitude;
- use Open-Meteo's free Forecast API for the PLATEAU AWARD demo;
- require no API key;
- request wind speed in `m/s`;
- retrieve:
  - `wind_speed_10m`;
  - `wind_direction_10m`;
  - `wind_gusts_10m`;
- interpret wind direction as meteorological **FROM** direction;
- convert mean wind speed/direction into an ENU physical vector;
- expose provider metadata to the browser UI;
- poll at a low rate independent of render rate and simulation rate;
- emit a Global Wind command only when the normalized command changes;
- preserve the last valid wind if the external API temporarily fails;
- visibly report stale/error state;
- support switching back to Manual mode without restarting the simulation.

### 2.2 Out of scope

The first implementation SHALL NOT:

- treat Open-Meteo as an observation station API;
- claim that the value is a measured wind at the venue;
- infer building wake, turbulence, updraft, or local street-canyon effects;
- query one weather value per Drone;
- query Open-Meteo every simulation step;
- query Open-Meteo every browser render frame;
- use `wind_gusts_10m` as an instantaneous physical gust;
- automatically create random gust waveforms from `wind_gusts_10m`;
- alter `hakoniwa-envsim`;
- add spatial wind fields;
- use browser geolocation as the authoritative show venue;
- silently fall back to zero wind on provider failure;
- use the weather result for real-aircraft operational or safety decisions.

Reproducible gust scenarios belong to the separate scenario producer described by WND-4.

---

## 3. Why Open-Meteo

Open-Meteo is selected for the PLATEAU AWARD implementation because it provides a low-friction
browser integration:

- free access for non-commercial use;
- no API key or signup required for the free endpoint;
- CORS support;
- WGS84 latitude/longitude input;
- global coverage;
- current wind speed and wind direction;
- 10 m wind gust value;
- selectable wind-speed unit including `m/s`;
- JSON over ordinary HTTP GET.

Open-Meteo combines weather-model outputs and automatically chooses suitable model data for the
requested location. The value used by this demo is therefore **model-derived current-condition
data**, not guaranteed on-site instrumentation.

The application UI and README MUST describe it accordingly.

---

## 4. External Service Contract

### 4.1 Endpoint

Free/non-commercial endpoint:

```text
https://api.open-meteo.com/v1/forecast
```

HTTP method:

```text
GET
```

Authentication:

```text
None
```

Request body:

```text
None
```

Expected response:

```text
application/json
```

### 4.2 Required query parameters

The provider adapter SHALL build the request with these parameters:

| Parameter | Value | Reason |
|---|---|---|
| `latitude` | venue latitude | WGS84 |
| `longitude` | venue longitude | WGS84 |
| `current` | `wind_speed_10m,wind_direction_10m,wind_gusts_10m` | minimum required wind fields |
| `wind_speed_unit` | `ms` | avoid km/h conversion in Hakoniwa |
| `timeformat` | `unixtime` | avoid local-time parsing ambiguity |
| `models` | omitted | omission selects the documented default/best-match model; the current API rejects explicit `models=auto` |
| `cell_selection` | `land` | PLATEAU venue is a land location |

Example conceptual request:

```text
GET /v1/forecast
    ?latitude=34.687
    &longitude=135.526
    &current=wind_speed_10m,wind_direction_10m,wind_gusts_10m
    &wind_speed_unit=ms
    &timeformat=unixtime
    &cell_selection=land
```

The implementation SHOULD build this URL with `URL` and `URLSearchParams`.
Do not construct the query with manual string concatenation.

### 4.3 Parameters intentionally not requested

The first implementation does not need:

- hourly forecasts;
- daily forecasts;
- precipitation;
- temperature;
- pressure;
- weather code;
- 80 m / 120 m / 180 m wind;
- historical weather.

Do not expand the request merely because Open-Meteo exposes additional fields.

The purpose of this adapter is **Global Wind**, not a general weather dashboard.

---

## 5. Expected Open-Meteo Response

A successful response is conceptually:

```json
{
  "latitude": 34.69,
  "longitude": 135.53,
  "generationtime_ms": 0.1,
  "utc_offset_seconds": 0,
  "timezone": "GMT",
  "timezone_abbreviation": "GMT",
  "elevation": 20.0,
  "current_units": {
    "time": "unixtime",
    "interval": "seconds",
    "wind_speed_10m": "m/s",
    "wind_direction_10m": "°",
    "wind_gusts_10m": "m/s"
  },
  "current": {
    "time": 1787865600,
    "interval": 900,
    "wind_speed_10m": 3.2,
    "wind_direction_10m": 18,
    "wind_gusts_10m": 5.8
  }
}
```

The exact numeric values and model resolution are provider-controlled.

The adapter SHALL NOT depend on undocumented fields.

---

## 6. Open-Meteo Response Validation

The adapter MUST reject a response unless all required structural and numeric checks pass.

### 6.1 Top-level checks

Require:

```text
response is an object
response.current is an object
response.current_units is an object
```

### 6.2 Unit checks

Require:

```text
current_units.wind_speed_10m == "m/s"
current_units.wind_gusts_10m == "m/s"
current_units.wind_direction_10m == "°"
```

If Open-Meteo changes or unexpectedly returns different units, fail closed.

Do not silently assume a unit.

### 6.3 Numeric checks

Require finite numbers:

```text
current.time
current.wind_speed_10m
current.wind_direction_10m
current.wind_gusts_10m
```

Reject:

- `NaN`;
- `Infinity`;
- `-Infinity`;
- strings where numbers are expected;
- missing fields;
- null values.

### 6.4 Range checks

Minimum recommended validation:

```text
0 <= wind_speed_10m <= MAX_PROVIDER_WIND_SPEED_M_S
0 <= wind_gusts_10m <= MAX_PROVIDER_WIND_SPEED_M_S
0 <= wind_direction_10m <= 360
```

Recommended initial guard:

```text
MAX_PROVIDER_WIND_SPEED_M_S = 100.0
```

This guard is not an operational safety limit.
It only prevents malformed or nonsensical external input from entering the simulator.

Normalize:

```text
360 deg -> 0 deg
```

### 6.5 Time checks

`current.time` is requested as Unix time.

Convert:

```javascript
const validAt = new Date(current.time * 1000).toISOString();
```

Store the browser fetch time independently:

```javascript
const fetchedAt = new Date().toISOString();
```

Do not call this field `observed_at`.

Open-Meteo current conditions are weather-model-derived data.
Use:

```text
valid_at
fetched_at
```

instead.

---

## 7. Semantics of Wind Direction

### 7.1 Open-Meteo direction

`wind_direction_10m` is interpreted as meteorological wind direction:

> the direction **FROM which** the wind is blowing.

Examples:

```text
0°   : wind from North
90°  : wind from East
180° : wind from South
270° : wind from West
```

Open-Meteoの取得値とLive詳細表示では、このFROM方位を保持する。一方、Manual操作と
共通コンパスは、ユーザーが直感的に操作できるよう、風が実際に流れるTO方位を使う:

```text
direction_to_deg = (direction_from_deg + 180) % 360
```

Live取得時はFROMとTOを併記し、コンパスの矢印はTOへ自動設定する。

### 7.2 Conversion to ENU physical vector

Hakoniwa Global Wind uses a vector indicating the direction in which air moves.

For:

```text
speed = s
meteorological FROM direction = theta
```

with `theta` measured clockwise from North:

```text
theta_rad = theta_deg * PI / 180

east_m_s  = -s * sin(theta_rad)
north_m_s = -s * cos(theta_rad)
up_m_s    = 0
```

Therefore:

| FROM direction | Air moves toward | ENU vector for `s=3` |
|---|---|---|
| North `0°` | South | `[0, -3, 0]` |
| East `90°` | West | `[-3, 0, 0]` |
| South `180°` | North | `[0, 3, 0]` |
| West `270°` | East | `[3, 0, 0]` |

Implementation:

```javascript
export function meteorologicalWindToEnu(speedMS, directionFromDeg) {
  const theta = directionFromDeg * Math.PI / 180.0;
  return [
    -speedMS * Math.sin(theta),
    -speedMS * Math.cos(theta),
    0.0,
  ];
}
```

Do not reuse a navigation-heading conversion without verifying the sign convention.

---

## 8. Gust Semantics

Open-Meteo `wind_gusts_10m` MUST NOT be interpreted as:

```text
"the wind speed that should be applied right now"
```

It is an aggregate/model gust metric for the relevant provider/model interval.

It also does not provide a separate instantaneous gust direction suitable for deterministic
physical application.

Therefore WND-3 SHALL use:

```text
wind_speed_10m + wind_direction_10m
```

as the physical Live wind.

`wind_gusts_10m` SHALL be treated as informational metadata only.

The UI MAY show:

```text
Wind      3.2 m/s
From      18°
Gust      5.8 m/s
```

but the Global Wind physical vector is derived from `3.2 m/s`, not `5.8 m/s`.

Actual gust simulation belongs to:

```text
Manual gust / Reproducible scenario
```

where timing and waveform are controlled by Hakoniwa virtual time.

This separation is intentional:

```text
Open-Meteo gust = weather information
Hakoniwa gust    = reproducible simulation input
```

---

## 9. Venue Coordinate Resolution

The weather query SHALL represent the **show venue**, not the browser operator location.

Priority:

1. use the resolved PLATEAU City World venue/origin coordinates produced during `configure`;
2. if a show-specific venue coordinate is already materialized into the generated browser config,
   use that resolved value;
3. for flat mode only, use the configured flat-world origin;
4. do not use `navigator.geolocation` as the Live-weather query source.

The current City experiment already has a PLATEAU `city_world_receipt` and separate AR venue
coordinates. The implementation should materialize one authoritative weather query coordinate
during `configure` so the browser does not need to rediscover repository/config semantics.

Recommended generated browser config:

```json
{
  "venue": {
    "latitude": 34.687,
    "longitude": 135.526,
    "source": "plateau-city-world"
  }
}
```

The adapter consumes only this resolved value.

Do not make the browser parse the City World receipt directly if `configure` can resolve it once.

---

## 10. Provider Adapter Output

The provider adapter SHOULD return a provider-neutral object first.

Example:

```json
{
  "provider": "open-meteo",
  "data_type": "forecast-model-current",
  "requested_location": {
    "latitude": 34.687,
    "longitude": 135.526
  },
  "resolved_location": {
    "latitude": 34.69,
    "longitude": 135.53,
    "elevation_m": 20
  },
  "valid_at": "2026-08-28T00:00:00.000Z",
  "fetched_at": "2026-08-28T00:03:12.450Z",
  "wind": {
    "speed_m_s": 3.2,
    "direction_from_deg": 18,
    "gust_m_s": 5.8,
    "vector_enu_m_s": [-0.989, -3.043, 0.0]
  }
}
```

This object is not itself a PDU frame.

A separate Global Wind producer maps it to Global Wind JSON v1.

This keeps:

```text
Open-Meteo schema
```

out of:

```text
Global Wind Asset
```

---

## 11. Global Wind Command Mapping

Recommended Live command:

```json
{
  "schema": "hakoniwa.drone-show/global-wind/v1",
  "publisher_id": "browser-7f3a9c2e",
  "sequence": 12,
  "source": {
    "mode": "live",
    "provider": "open-meteo",
    "observed_at": "2026-08-28T00:00:00.000Z"
  },
  "wind": {
    "enabled": true,
    "vector_ros_m_s": [-3.043, 0.989, 0.0],
    "variation": {
      "speed_stddev_m_s": 0.0,
      "seed": 1
    }
  }
}
```

Normative physical truth:

```text
wind.enabled
wind.vector_ros_m_s
wind.variation
```

Display fields retained in the browser-side provider result (not duplicated into the PDU):

```text
speed_m_s
direction_from_deg / direction_to_deg
gust_m_s
valid_at / fetched_at
```

Provider内部では標準ENUベクトルを保持できるが、既存Global Wind v1へ送る時点でDrone PDUの
ROS座標へ変換する。receiverは`vector_ros_m_s`を物理入力として使用する。

The receiver MUST NOT reconstruct the physical vector from browser display metadata.

---

## 12. Polling Policy

### 12.1 Independent clocks

These frequencies MUST remain independent:

```text
Browser render loop        : e.g. 60 Hz
Hakoniwa simulation        : simulation-defined
Global Wind Asset polling  : Hakoniwa timing loop
Open-Meteo HTTP fetch      : 5 minutes by default
```

No faster layer SHALL force the Open-Meteo fetch layer to run faster.

### 12.2 Default interval

Initial default:

```text
OPEN_METEO_POLL_INTERVAL_MS = 5 * 60 * 1000
```

The interval MAY be configurable, but the first UI does not need a user-facing polling-frequency
control.

### 12.3 Initial fetch

When the user changes mode:

```text
Manual -> Live
```

perform an immediate fetch.

Do not wait five minutes for the first Live value.

### 12.4 Overlapping requests

Never allow two Open-Meteo requests from the same provider instance to overlap.

If a poll timer fires while a request is active:

```text
skip this poll
```

Do not queue multiple fetches.

---

## 13. HTTP Timeout and Failure Handling

### 13.1 Timeout

Recommended fetch timeout:

```text
5 seconds
```

Use `AbortController`.

Example:

```javascript
async function fetchWithTimeout(url, timeoutMs = 5000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      method: 'GET',
      signal: controller.signal,
      cache: 'no-store',
    });
  } finally {
    clearTimeout(timer);
  }
}
```

### 13.2 HTTP failures

Treat as provider failure:

```text
network exception
timeout
HTTP !2xx
invalid JSON
Open-Meteo error response
schema validation failure
unit validation failure
numeric/range validation failure
```

### 13.3 Failure policy with a previous valid value

If Live mode already has a valid applied value:

```text
KEEP the last valid Global Wind
DO NOT emit zero wind
DO NOT increment Global Wind sequence
DO NOT repeatedly rewrite Disturbance PDUs
mark provider/UI state as stale/error
```

This avoids turning a network outage into a physical wind discontinuity.

### 13.4 Failure policy before the first valid value

If the user selects Live mode but the first fetch fails:

```text
do not emit a new Live Global Wind command
keep the previously applied Manual/zero state
show Live provider error
allow Retry
allow switching back to Manual
```

Do not pretend Live mode is physically active before valid data exists.

### 13.5 Retry

Do not implement an aggressive automatic retry loop.

Recommended first implementation:

```text
normal poll: 5 min
manual Retry button: immediate
```

Optionally one delayed retry may be added later.

---

## 14. Staleness

Track:

```text
last_successful_fetch_at
provider_valid_at
```

Recommended UI staleness threshold:

```text
15 minutes
```

State examples:

```text
LIVE / OK
LIVE / STALE
LIVE / ERROR
LIVE / FETCHING
MANUAL
```

A stale value may remain physically applied for the demo.

The UI MUST make staleness visible.

Do not silently reinterpret a stale value as fresh.

---

## 15. Change Detection and Sequence Rules

The central performance rule remains:

> HTTP polling does not imply PDU writing.

The provider may fetch a new response every five minutes while the physical wind remains unchanged.

### 15.1 Publisher ID

At page load:

```javascript
const publisherId = `browser-${crypto.randomUUID().replaceAll('-', '').slice(0, 8)}`;
```

A browser reload creates a new publisher ID.

### 15.2 Sequence

Start locally at:

```text
0
```

Increment immediately before a new Global Wind command is actually transmitted:

```text
1, 2, 3, ...
```

Do not increment merely because:

- the UI rendered;
- a poll timer fired;
- an HTTP request completed;
- `fetched_at` changed.

### 15.3 Normalized command identity

The decision to send SHOULD be based on stable command semantics, not volatile metadata.

Recommended comparison fields:

```text
source.mode
source.provider
wind.enabled
normalized vector_ros_m_s
wind.variation
```

Do not include:

```text
fetched_at
HTTP latency
generationtime_ms
```

in change detection.

`valid_at` MAY be excluded from physical change detection.

### 15.4 Floating-point normalization

To avoid tiny floating-point differences caused by trigonometric conversion, canonicalize the
physical vector before comparison.

Recommended resolution:

```text
0.001 m/s
```

Example:

```javascript
function roundWind(value) {
  return Math.round(value * 1000) / 1000;
}
```

Normalize each ENU component.

### 15.5 Manual -> Live switch

Even if Manual and Live happen to produce the same physical vector, switching source mode SHOULD
emit one command so the current source/audit state becomes Live.

### 15.6 Repeated Live result

If a new Open-Meteo response contains the same normalized physical wind:

```text
update UI/provider metadata
do not increment Global Wind sequence
do not send command PDU
```

---

## 16. Browser State Model

Recommended internal state:

```javascript
{
  selectedMode: 'manual' | 'live',

  publisherId: 'browser-...',
  nextSequence: 1,

  appliedCommandKey: null,

  live: {
    status: 'idle' | 'fetching' | 'ok' | 'stale' | 'error',
    lastResult: null,
    lastSuccessAt: null,
    lastError: null,
    requestInFlight: false
  }
}
```

Do not use DOM elements as the authoritative state store.

---

## 17. Proposed Browser Module Boundary

Recommended new modules:

```text
web/
  global-wind/
    global-wind-model.mjs
    global-wind-pdu-codec.mjs
    global-wind-controller.mjs
    providers/
      open-meteo.mjs
```

Responsibilities:

### `providers/open-meteo.mjs`

Owns only:

- Open-Meteo URL construction;
- HTTP fetch;
- Open-Meteo response validation;
- unit validation;
- model-data metadata;
- meteorological direction normalization;
- conversion to provider-neutral wind result.

It MUST NOT:

- know SHM;
- know Drone IDs;
- know Disturbance;
- know `hakopy`;
- write WebBridge frames directly.

### `global-wind-model.mjs`

Owns:

- provider-neutral -> Global Wind command mapping;
- ENU vector canonicalization;
- command-change comparison;
- sequence/publisher semantics.

### `global-wind-pdu-codec.mjs`

Owns:

- fixed-size frame codec;
- magic;
- length;
- padding;
- JSON validation;
- Global Wind protocol-specific checks.

The implementation SHOULD mirror the existing Drone Show control codec style rather than inventing
a new binary convention.

### `global-wind-controller.mjs`

Owns:

- Manual/Live mode switch;
- provider polling lifecycle;
- retry;
- stale timer;
- UI state;
- deciding whether a command should be sent.

---

## 18. PDU Framing

The existing Drone Show control protocol uses a fixed 1024-byte frame with:

```text
4-byte magic
2-byte big-endian JSON length
2-byte flags
UTF-8 JSON
zero padding
```

Global Wind SHOULD follow the same structural convention.

Use a distinct magic so a wind frame can never be mistaken for a Show Control frame.

Current implementation:

```text
HDW1
```

Frame:

| offset | size | content |
|---:|---:|---|
| 0 | 4 | ASCII `HDW1` |
| 4 | 2 | JSON byte length, big-endian uint16 |
| 6 | 2 | flags = 0 |
| 8 | 0..1016 | UTF-8 JSON |
| rest | variable | zero padding |

Recommended size:

```text
1024 bytes
```

Do not modify `HDS1` / Show Control semantics.

Global Wind owns a separate PDU slot and protocol.

---

## 19. Global Wind Command Validation

Browser and Python side SHOULD enforce equivalent validation.

Required top-level keys:

```text
schema
publisher_id
sequence
source
wind
```

Recommended checks:

```text
schema == "hakoniwa.drone-show/global-wind/v1"

publisher_id:
    string
    1..64 chars
    restricted printable identifier

sequence:
    positive safe integer

source.mode:
    "manual" | "live" | "scenario"

source.provider:
    null for manual/scenario if appropriate
    "open-meteo" for Open-Meteo Live

wind.enabled:
    boolean

wind.vector_ros_m_s:
    exactly 3 finite numbers
    reasonable configured range

wind.variation.speed_stddev_m_s:
    finite and >= 0

wind.variation.seed:
    non-negative safe integer
```

平均風速、FROM/TO方位、gust、valid/fetched timeはブラウザのprovider状態として保持し、
strictな物理PDUへ重複して格納しない。

Unknown fields SHOULD be rejected in v1 if the rest of the Show protocols follow strict schemas.

---

## 20. Suggested Open-Meteo Adapter API

```javascript
export class OpenMeteoProvider {
  constructor({
    fetchImpl = fetch,
    timeoutMs = 5000,
    maxWindSpeedMS = 100.0,
  } = {}) {
    // ...
  }

  buildUrl({ latitude, longitude }) {
    // returns URL
  }

  async fetchCurrentWind({ latitude, longitude }) {
    // returns provider-neutral normalized result
  }
}
```

Expected return:

```javascript
{
  provider: 'open-meteo',
  dataType: 'forecast-model-current',
  requestedLocation: {
    latitude,
    longitude,
  },
  resolvedLocation: {
    latitude: response.latitude,
    longitude: response.longitude,
    elevationM: response.elevation,
  },
  validAt: new Date(response.current.time * 1000).toISOString(),
  fetchedAt: new Date().toISOString(),
  wind: {
    speedMS,
    directionFromDeg,
    gustMS,
    vectorEnuMS,
  },
}
```

Errors SHOULD use a provider-specific error class:

```javascript
export class OpenMeteoProviderError extends Error {
  constructor(code, message, cause = undefined) {
    super(message, { cause });
    this.name = 'OpenMeteoProviderError';
    this.code = code;
  }
}
```

Suggested codes:

```text
NETWORK
TIMEOUT
HTTP
JSON
SCHEMA
UNIT
RANGE
```

This makes UI messages deterministic and testable.

---

## 21. UI External Specification

Live weather UI minimum:

```text
[ Manual ] [ Live ]

Live Weather
Provider: Open-Meteo
Status: LIVE / OK
Venue: Osaka / 34.687, 135.526
Wind: 3.2 m/s
Direction: 18° from NNE
Gust: 5.8 m/s
Valid: 2026-08-28 ...
Updated: just now

[ Retry ]
```

The exact visual design is non-normative.

### 21.1 Required information

When Live has a successful value, show:

- mode = Live;
- provider = Open-Meteo;
- requested venue coordinate;
- mean wind speed;
- meteorological FROM direction;
- gust reference value;
- data valid time;
- last successful fetch time;
- stale/error status if applicable.

### 21.2 Attribution

Show visible attribution in the weather panel or an adjacent information area:

```text
Weather data: Open-Meteo
```

README SHALL include the full licence/usage note.

### 21.3 Warning

The UI SHOULD include a concise note such as:

```text
Model weather for simulation demo; not for real-flight decisions.
```

Do not label the value as:

```text
measured wind
actual on-site wind
real-time sensor wind
```

---

## 22. Manual / Live State Transition

### Manual -> Live

```text
1. User selects Live.
2. UI enters LIVE/FETCHING.
3. Perform immediate Open-Meteo fetch.
4. Validate and normalize response.
5. Build Global Wind command.
6. If semantic command differs from currently applied command:
      sequence++
      send one PDU
7. Mark LIVE/OK.
8. Start 5-minute poll timer.
```

If step 3-4 fails:

```text
keep previously applied wind
show LIVE/ERROR
do not send a PDU
```

### Live -> Manual

```text
1. Stop Live poll timer.
2. Abort in-flight Live request if possible.
3. Switch selected mode to Manual.
4. Apply current Manual controls as one Global Wind command.
5. sequence++
6. send one PDU.
```

### Live -> Live repeated poll

```text
1. Fetch.
2. Validate.
3. Update weather display metadata.
4. Compare normalized command.
5. Send only if changed.
```

---

## 23. Interaction with Global Wind Asset

The Open-Meteo provider SHALL NOT change the Global Wind Asset loop contract.

The asset still:

```text
hakopy.usleep(...)
nonblocking command check
```

and writes Drone Disturbance only when:

- initial wind must be distributed;
- reset requires reapplication;
- a new accepted Global Wind command changes current wind.

Open-Meteo HTTP latency must never block Hakoniwa simulation because HTTP lives in the browser,
not the Python simulation asset.

This is a key architectural property.

---

## 24. Reset Behavior

Open-Meteo MUST NOT be refetched because Hakoniwa reset occurred.

Reset is a simulator lifecycle event, not a weather-provider event.

Expected behavior:

```text
Browser:
    keeps current Live provider state
    keeps normal provider polling interval

Global Wind Asset:
    detects/reset lifecycle according to WND-0/WND-1
    reapplies currently stored Global Wind to all Drone Disturbance PDUs once
```

This avoids unnecessary external API calls and preserves deterministic runtime behavior around reset.

---

## 25. Configure-Time Integration

`configure` SHOULD materialize everything the browser needs.

Recommended generated config:

```json
{
  "global_wind": {
    "enabled": true,
    "initial_mode": "manual",
    "manual": {
      "enabled": false,
      "speed_m_s": 0.0,
      "direction_to_deg": 0.0,
      "speed_stddev_m_s": 0.0
    },
    "live": {
      "provider": "open-meteo",
      "poll_interval_sec": 300,
      "timeout_sec": 5,
      "stale_after_sec": 900
    },
    "venue": {
      "latitude": 34.687,
      "longitude": 135.526,
      "source": "plateau-city-world"
    }
  }
}
```

Do not hard-code Osaka coordinates in the browser source.

The same code must work when the City receipt changes to another PLATEAU city.

---

## 26. Suggested Experiment YAML

The exact final schema may be adjusted to existing config style, but the intent SHOULD resemble:

```yaml
global_wind:
  enabled: true
  initial_mode: manual

  manual:
    enabled: false
    speed_m_s: 0.0
    direction_to_deg: 0.0
    speed_stddev_m_s: 0.0

  live:
    provider: open-meteo
    poll_interval_sec: 300
    timeout_sec: 5
    stale_after_sec: 900
```

Venue coordinates SHOULD normally come from the resolved City World and not be duplicated here.

An explicit override MAY later be added for testing:

```yaml
  venue_override:
    latitude: 34.687
    longitude: 135.526
```

but this is not required for the first implementation.

---

## 27. Testing Strategy

### 27.1 Unit: URL construction

Input:

```text
latitude = 34.687
longitude = 135.526
```

Verify exact semantic parameters:

```text
current has all 3 wind variables
wind_speed_unit == ms
timeformat == unixtime
models is omitted so the provider default/best match is used
cell_selection == land
```

Do not test query-parameter ordering.

### 27.2 Unit: North wind

Input:

```json
{
  "wind_speed_10m": 3.0,
  "wind_direction_10m": 0.0
}
```

Expected:

```text
vector ENU ~= [0, -3, 0]
```

### 27.3 Unit: East wind

Input:

```text
speed = 3
from = 90°
```

Expected:

```text
[-3, 0, 0]
```

### 27.4 Unit: South wind

Expected:

```text
[0, +3, 0]
```

### 27.5 Unit: West wind

Expected:

```text
[+3, 0, 0]
```

### 27.6 Unit: 360 normalization

Input:

```text
direction = 360
```

Expected:

```text
direction = 0
```

### 27.7 Unit: invalid numeric values

Reject each:

```text
NaN
Infinity
null
"3.0"
-1 wind speed
```

### 27.8 Unit: wrong units

Response:

```json
{
  "current_units": {
    "wind_speed_10m": "km/h"
  }
}
```

Expected:

```text
provider error: UNIT
```

No implicit conversion in this failure test because the request explicitly asked for `m/s`.

### 27.9 Unit: unchanged value

Two successful fetches with the same normalized vector.

Expected:

```text
provider UI metadata updates
Global Wind sequence unchanged
no WebBridge command write
```

### 27.10 Unit: tiny floating-point difference

Two vectors differing below the 0.001 m/s canonicalization threshold.

Expected:

```text
no command send
```

### 27.11 Unit: physical change

Wind changes from:

```text
3.0 m/s from North
```

to:

```text
4.0 m/s from North
```

Expected:

```text
sequence + 1
exactly one Global Wind command
```

### 27.12 Unit: mode change with identical vector

Manual:

```text
3.0 m/s from North
```

Live:

```text
3.0 m/s from North
```

Expected:

```text
one command sent because source.mode changed
```

### 27.13 Failure: timeout with previous value

Expected:

```text
last physical wind preserved
no sequence increment
no command send
UI = LIVE/ERROR or LIVE/STALE
```

### 27.14 Failure: first Live fetch fails

Expected:

```text
previous Manual/zero state preserved
no Live command sent
Retry available
```

### 27.15 Integration: no simulation coupling

While Open-Meteo request is artificially delayed:

```text
Hakoniwa simulation continues
Global Wind Asset continues hakopy.usleep()
Drone runtime continues
```

### 27.16 Integration: reset

With Live wind already active:

```text
reset Hakoniwa
do not fetch Open-Meteo due to reset
Global Wind Asset reapplies stored wind once
```

---

## 28. Browser Mock for Deterministic Tests

Automated tests MUST NOT depend on the public Open-Meteo service.

Provide fixture responses.

Example fixture:

```text
tests/fixtures/open-meteo/current-wind.json
```

Mock `fetch`.

Test at least:

```text
success
HTTP 400
HTTP 500
timeout
invalid JSON
missing current
wrong units
NaN-like invalid field handling
direction boundary
```

Public API access may be used only as an optional manual smoke test.

---

## 29. Manual Smoke Test

A developer smoke test MAY:

1. configure a PLATEAU City show;
2. open the City Viewer;
3. switch Manual -> Live;
4. confirm Open-Meteo provider state;
5. confirm venue coordinates;
6. confirm one new Global Wind PDU;
7. inspect all Drone Disturbance values;
8. wait for a second provider poll or invoke Retry;
9. confirm unchanged wind does not fan out again;
10. modify Manual wind;
11. switch back to Live;
12. confirm one Live reapplication.

Record enough diagnostics to distinguish:

```text
HTTP fetch count
Global Wind command count
Disturbance fan-out count
```

These are three different counters.

---

## 30. Logging

Browser debug logging SHOULD have a stable prefix:

```text
[global-wind]
[open-meteo]
```

Useful events:

```text
provider fetch start
provider fetch success
provider fetch failure
provider result unchanged
global wind command sent
mode changed
stale threshold reached
retry requested
```

Do not log every animation frame.

Do not log every Global Wind Asset simulation loop.

---

## 31. Metrics for WND-3 Acceptance

WND-3 is complete when:

- Open-Meteo is fetched using the configured PLATEAU venue;
- no API key is required for the demo;
- wind is obtained in `m/s`;
- wind direction is interpreted as meteorological FROM;
- the ENU vector passes cardinal-direction tests;
- the browser displays provider, valid time, speed, direction, and gust;
- switching to Live applies one Global Wind command;
- repeated identical provider values do not produce new PDU writes;
- provider failure preserves the last valid physical wind;
- Manual mode remains usable after Live failure;
- no provider code exists in the Python Global Wind Asset;
- no Drone position is read for this feature;
- no Open-Meteo request is coupled to simulation frequency;
- no real-flight safety claim is made.

---

## 32. README / Licence Note

For the PLATEAU AWARD demo, README SHALL state at least:

```text
The Live Weather demo uses the Open-Meteo Free API.

Open-Meteo Free API access is intended for non-commercial use and is subject to
Open-Meteo's current Terms of Use and rate limits. Weather data is provided under
CC BY 4.0 with attribution.

This project uses model-derived weather information for simulation and demonstration
purposes only. It is not intended for actual flight-operation, aviation-weather, or
safety decisions.

If this feature is used in a commercial product or service, the Open-Meteo usage
conditions and API plan must be reviewed separately.
```

Do not hard-code today's terms into code behavior.

Terms can change; README should point maintainers to the provider's official terms.

---

## 33. Current Free-API Constraints Relevant to the Demo

At the time this implementation specification was prepared, Open-Meteo documents the free API as:

```text
non-commercial use
no API key
less than 10,000 calls/day
less than 5,000 calls/hour
less than 600 calls/minute
CC BY 4.0 attribution
```

With a 5-minute poll interval:

```text
12 calls/hour
288 calls/day
```

per continuously open browser.

This is far below the documented free limits for the intended award demo.

Nevertheless, do not intentionally open many independent polling pages against the public API.

---

## 34. Source References

Implementation should be verified against the current official documents when modified:

- Open-Meteo Forecast API documentation  
  `https://open-meteo.com/en/docs`

- Open-Meteo Terms of Use  
  `https://open-meteo.com/en/terms`

- Open-Meteo project / API information  
  `https://open-meteo.com/`

- Open-Meteo OpenAPI specification  
  `https://github.com/open-meteo/open-meteo/blob/main/openapi/forecast.yml`

The official documentation is the authority if this document and the provider later diverge.

---

## 35. Recommended Implementation Order for Codex

Implement in this order and do not broaden scope before each step passes.

### Step 1: Pure conversion

Add and test:

```text
meteorologicalWindToEnu()
direction normalization
vector rounding
```

No HTTP and no PDU yet.

### Step 2: Open-Meteo parser

Add fixture-driven:

```text
validateOpenMeteoResponse()
normalizeOpenMeteoResponse()
```

No live network dependency in tests.

### Step 3: URL + fetch adapter

Add:

```text
OpenMeteoProvider.buildUrl()
OpenMeteoProvider.fetchCurrentWind()
timeout
error mapping
```

### Step 4: Live controller

Add:

```text
Manual / Live state
immediate first fetch
5-minute polling
no overlapping fetches
Retry
stale state
```

### Step 5: Global Wind mapping

Map provider-neutral result to Global Wind JSON v1.

Verify:

```text
sequence increments only on an emitted command
identical provider result does not emit
mode switch emits
```

### Step 6: WebBridge / PDU

Connect the existing show WebBridge path to the Global Wind command PDU.

Do not introduce a second HTTP/WebSocket server merely for weather.

### Step 7: UI

Expose:

```text
Manual / Live
provider
status
speed
direction FROM
gust
valid time
last update
Retry
attribution
warning
```

### Step 8: Integration test

Run with the real Global Wind Asset and many drones.

Verify that Open-Meteo polling never creates per-simulation-step work.

---

## 36. Hard Design Rules

Codex MUST preserve these rules unless the specification is explicitly revised:

1. **One weather query per show, never per Drone.**
2. **The weather provider runs in the browser-side producer layer, not the simulation asset.**
3. **Open-Meteo mean 10 m wind drives Live physics.**
4. **Open-Meteo gust is metadata, not an instantaneous gust waveform.**
5. **Meteorological FROM direction must be converted to the direction air travels in ENU.**
6. **The venue coordinate is the show venue, not the browser device location.**
7. **HTTP polling is independent of simulation and render frequency.**
8. **A successful HTTP fetch does not automatically mean a PDU write.**
9. **Unchanged normalized wind produces no new Global Wind command.**
10. **Provider failure preserves the last valid wind.**
11. **Reset does not trigger a weather HTTP request.**
12. **No external API latency may block Hakoniwa virtual time.**
13. **Do not modify `hakoniwa-envsim` for this Global Wind feature.**
14. **Do not add spatial search or Drone Pose reads.**
15. **Do not claim real-flight safety or actual on-site observed weather.**

---

## 37. Definition of Done

The feature is done when a user can:

```text
1. configure any supported PLATEAU City show;
2. start the show runtime;
3. open the browser;
4. select Live Weather;
5. see the venue's Open-Meteo model wind;
6. see that wind converted to Global Wind;
7. fly the whole fleet under that one physical wind;
8. switch back to Manual;
9. continue the simulation without restarting;
```

and diagnostics demonstrate:

```text
Open-Meteo HTTP request count << simulation step count
Global Wind command count << browser frame count
Disturbance fan-out occurs only when Global Wind actually changes or must be reapplied
```

That property is more important than adding additional weather fields.
