import { decodeFrame, encodeFrame, startCommand } from './show-pdu-codec.mjs';

export class ShowControlClient {
  constructor(manager, config, onStatus) {
    this.manager = manager;
    this.config = config;
    this.onStatus = onStatus;
    this.status = null;
    this.lastStatusSequence = 0;
    this.commandSequence = 0;
    this.pollTimer = null;
  }

  async start() {
    const control = this.config.control;
    const statusDeclared = await this.manager.declare_pdu_for_read(
      control.robot_name, control.status_pdu_name,
    );
    const commandDeclared = await this.manager.declare_pdu_for_write(
      control.robot_name, control.command_pdu_name,
    );
    if (!statusDeclared || !commandDeclared) {
      throw new Error('Drone Show control PDU declaration failed');
    }
    this.pollTimer = window.setInterval(() => this.poll(), 100);
    this.poll();
  }

  stop() {
    if (this.pollTimer !== null) window.clearInterval(this.pollTimer);
    this.pollTimer = null;
  }

  poll() {
    const control = this.config.control;
    const raw = this.manager.read_pdu_raw_data(
      control.robot_name, control.status_pdu_name,
    );
    if (!raw) return;
    try {
      const status = decodeFrame(raw);
      if (!status || status.kind !== 'status' || status.sequence <= this.lastStatusSequence) return;
      this.status = status;
      this.lastStatusSequence = status.sequence;
      this.onStatus(status);
    } catch (error) {
      this.onStatus({ state: 'failed', error: `Status PDU: ${error.message}` });
    }
  }

  async requestStart() {
    if (!this.status || this.status.state !== 'waiting') {
      throw new Error('Show Runner is not waiting for START');
    }
    this.commandSequence += 1;
    const frame = encodeFrame(startCommand(this.status, this.commandSequence));
    const control = this.config.control;
    const sent = await this.manager.flush_pdu_raw_data(
      control.robot_name, control.command_pdu_name, frame,
    );
    if (!sent) throw new Error('START command send failed');
  }
}
