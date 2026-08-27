import {
  ROBOT_NAME,
  COMMAND_PDU_NAME,
  createPublisherId,
  encodeFrame,
  manualWindCommand,
  liveWindCommand,
  physicalWindKey,
} from './global-wind-protocol.mjs';

export class GlobalWindClient {
  constructor(manager, config = {}) {
    this.manager = manager;
    this.robotName = config.robot_name ?? ROBOT_NAME;
    this.commandPduName = config.command_pdu_name ?? COMMAND_PDU_NAME;
    this.publisherId = createPublisherId();
    this.sequence = 0;
    this.lastPhysicalKey = null;
  }

  async start() {
    const declared = await this.manager.declare_pdu_for_write(
      this.robotName, this.commandPduName,
    );
    if (!declared) throw new Error('Global Wind command PDU declaration failed');
  }

  async sendManual({ enabled, directionToDeg, speedMps, speedStddevMps }) {
    const command = manualWindCommand({
      publisherId: this.publisherId,
      sequence: this.sequence + 1,
      enabled,
      directionToDeg,
      speedMps,
      speedStddevMps,
    });
    return this.#send(command);
  }

  async sendLive({ provider, validAt, vectorRosMS, speedStddevMps }) {
    const command = liveWindCommand({
      publisherId: this.publisherId,
      sequence: this.sequence + 1,
      provider,
      validAt,
      vectorRosMS,
      speedStddevMps,
    });
    return this.#send(command);
  }

  async #send(command) {
    const key = physicalWindKey(command);
    if (key === this.lastPhysicalKey) return { sent: false, command };
    const sent = await this.manager.flush_pdu_raw_data(
      this.robotName, this.commandPduName, encodeFrame(command),
    );
    if (!sent) throw new Error('Global Wind command send failed');
    this.sequence = command.sequence;
    this.lastPhysicalKey = key;
    return { sent: true, command };
  }
}
