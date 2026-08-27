import { meteorologicalWindToRos } from './global-wind-protocol.mjs';

function semanticKey(result, vectorRosMS, speedStddevMps) {
  return JSON.stringify([
    result.provider,
    vectorRosMS.map((value) => Math.round(value * 1000) / 1000),
    Number(speedStddevMps),
  ]);
}

export class GlobalWindLiveController {
  constructor({
    client,
    provider,
    venue,
    pollIntervalSec = 300,
    staleAfterSec = 900,
    getSpeedStddevMps = () => 0,
    onState = () => {},
  }) {
    this.client = client;
    this.provider = provider;
    this.venue = venue;
    this.pollIntervalMs = pollIntervalSec * 1000;
    this.staleAfterMs = staleAfterSec * 1000;
    this.getSpeedStddevMps = getSpeedStddevMps;
    this.onState = onState;
    this.active = false;
    this.requestInFlight = false;
    this.pollTimer = null;
    this.staleTimer = null;
    this.generation = 0;
    this.appliedKey = null;
    this.state = {
      mode: 'manual', status: 'idle', lastResult: null,
      lastSuccessAt: null, lastError: null, lastCommandSent: false,
    };
  }

  sourceUrl() {
    return this.provider.buildUrl(this.venue).toString();
  }

  snapshot() {
    return { ...this.state, requestInFlight: this.requestInFlight };
  }

  #emit() {
    this.onState(this.snapshot());
  }

  async activate() {
    if (this.active) return this.refresh();
    this.active = true;
    this.generation += 1;
    this.appliedKey = null;
    this.state = { ...this.state, mode: 'live', status: 'fetching', lastError: null };
    this.#emit();
    this.pollTimer = globalThis.setInterval(() => { void this.refresh(); }, this.pollIntervalMs);
    return this.refresh();
  }

  deactivate() {
    this.active = false;
    this.generation += 1;
    this.provider.abort?.();
    if (this.pollTimer !== null) globalThis.clearInterval(this.pollTimer);
    if (this.staleTimer !== null) globalThis.clearTimeout(this.staleTimer);
    this.pollTimer = null;
    this.staleTimer = null;
    this.state = { ...this.state, mode: 'manual', status: 'idle', lastError: null };
    this.#emit();
  }

  async refresh() {
    if (!this.active || this.requestInFlight) return { skipped: true };
    const generation = this.generation;
    this.requestInFlight = true;
    this.state = { ...this.state, status: 'fetching', lastError: null };
    this.#emit();
    try {
      const result = await this.provider.fetchCurrentWind(this.venue);
      if (!this.active || generation !== this.generation) return { discarded: true };
      const vectorRosMS = meteorologicalWindToRos(
        result.wind.directionFromDeg, result.wind.speedMS,
      );
      const stddev = Number(this.getSpeedStddevMps());
      const key = semanticKey(result, vectorRosMS, stddev);
      let sent = false;
      if (key !== this.appliedKey) {
        const applied = await this.client.sendLive({
          provider: result.provider,
          validAt: result.validAt,
          vectorRosMS,
          speedStddevMps: stddev,
        });
        sent = applied.sent;
        this.appliedKey = key;
      }
      const now = new Date().toISOString();
      this.state = {
        ...this.state,
        status: 'ok', lastResult: result, lastSuccessAt: now,
        lastError: null, lastCommandSent: sent,
      };
      this.#scheduleStale(generation);
      this.#emit();
      return { sent, result };
    } catch (error) {
      if (!this.active || generation !== this.generation) return { discarded: true };
      this.state = {
        ...this.state,
        status: 'error', lastError: error,
        lastCommandSent: false,
      };
      this.#emit();
      return { error };
    } finally {
      this.requestInFlight = false;
      this.#emit();
    }
  }

  async setSpeedStddevMps() {
    if (!this.active || !this.state.lastResult) return { skipped: true };
    const result = this.state.lastResult;
    const vectorRosMS = meteorologicalWindToRos(
      result.wind.directionFromDeg, result.wind.speedMS,
    );
    const stddev = Number(this.getSpeedStddevMps());
    const key = semanticKey(result, vectorRosMS, stddev);
    if (key === this.appliedKey) return { sent: false };
    const applied = await this.client.sendLive({
      provider: result.provider,
      validAt: result.validAt,
      vectorRosMS,
      speedStddevMps: stddev,
    });
    this.appliedKey = key;
    this.state = { ...this.state, lastCommandSent: applied.sent };
    this.#emit();
    return applied;
  }

  #scheduleStale(generation) {
    if (this.staleTimer !== null) globalThis.clearTimeout(this.staleTimer);
    this.staleTimer = globalThis.setTimeout(() => {
      if (!this.active || generation !== this.generation) return;
      this.state = { ...this.state, status: 'stale' };
      this.#emit();
    }, this.staleAfterMs);
  }
}
