# Drone Show Control Protocol v1

## 目的

ブラウザの表示と全機の初期位置確認が終わるまで、Show Experience Runnerの
飛行フェーズを開始しないための通信契約です。既存のVisual State PDU、ICRA Recipe、
Drone PROのShow Runnerは変更しません。

通信は既存WebBridgeのWebSocket（既定`ws://127.0.0.1:8765`）へ相乗りします。
ブラウザとRunnerの間に別のWebSocket serverは設けません。

```text
Browser -- START JSON frame --> WebBridge -- SHM --> Show Experience Runner
Browser <-- status JSON frame -- WebBridge <-- SHM -- Show Experience Runner
```

## SHM PDU

| robot | channel | name | direction | size |
|---|---:|---|---|---:|
| `DroneShow` | 0 | `show_command` | Browser -> Runner | 1024 byte |
| `DroneShow` | 1 | `show_status` | Runner -> Browser | 1024 byte |

CommandとStatusは別のSHM slotを使用します。同じslotを双方向利用した場合に、
書き込みが相手の未読データを上書きする問題を避けるためです。

## 固定長frame

SHM slotは固定長、JSONは可変長なので、1024 byteを次のように構成します。

| offset | size | 内容 |
|---:|---:|---|
| 0 | 4 | magic ASCII `HDS1` |
| 4 | 2 | JSON byte長、big endian unsigned integer |
| 6 | 2 | flags、v1では常に0 |
| 8 | 0..1016 | UTF-8 JSON |
| 残り | 可変 | 0 padding |

送信側は常に1024 byteを書きます。受信側はmagic、flags、長さ、UTF-8、JSON、
0 paddingおよびmessage schemaをすべて検証します。全byteが0の未書き込みslotは
messageなしとして扱います。

## START command

```json
{
  "schema_version": 1,
  "protocol": "hakoniwa.drone-show-control",
  "kind": "command",
  "type": "START",
  "run_id": "32文字の小文字16進数",
  "show_sha256": "64文字の小文字16進数",
  "sequence": 1
}
```

Runnerは現在の`run_id`と`show_sha256`が一致し、未受理のsequenceを持つSTARTだけを
一度受理します。以前の起動でSHMに残ったcommand、別のshowに対するcommand、連打や
再送による重複commandは飛行を開始しません。

## Status

Task 1ではUI復元に必要な最小状態だけを通知します。

```json
{
  "schema_version": 1,
  "protocol": "hakoniwa.drone-show-control",
  "kind": "status",
  "state": "waiting",
  "run_id": "32文字の小文字16進数",
  "show_sha256": "64文字の小文字16進数",
  "sequence": 3,
  "simulation_time_usec": 1234560,
  "show_time_usec": 250000,
  "show_frame_index": 1
}
```

`state`は`initializing`、`waiting`、`running`、`completed`、`failed`のいずれかです。
`failed`だけは1..256文字の`error`を持ちます。状態変化時は即時、同じ状態の間は
既定4 Hz（約250 ms間隔）で更新します。Show IR実行時の`show_frame_index`は、Viewerが表示すべきresolved
frameを示します。移動中は出発frameを維持し、目的frameへの到着時に更新されます。
`simulation_time_usec`は箱庭の絶対仮想時刻です。任意fieldの`show_time_usec`は、離陸完了後に
Show IRの時系列実行を開始した時点を0とする箱庭時刻です。開始前は省略し、Wind Scenario等の
時系列処理はwall clockではなくこの値を正本にします。旧`show.json`経路ではShow IR固有の
任意fieldを省略します。

ブラウザは同じ`run_id`のStatusだけを`sequence`で順序判定します。Runner再起動により
`run_id`が変わった場合はsequence基準をリセットし、新しい実行のsequence=1から受理します。
START送信後もRunnerが`waiting`のまま3秒経過した場合は、通信ロストから回復できるよう
開始ボタンを再度有効化します。Runner側のrun_idとsequence検証により再送は冪等です。

## 待機と箱庭時刻

Show Experience Runnerはsocketを直接待ち受けません。各manual timing loopでSHMを
非blockingに確認し、START待機中も必ず`hakopy.usleep(delta_time_usec)`を呼びます。
これにより、ブラウザ操作待ちが箱庭全体のシミュレーション時刻を停止させません。

## 実装の正本

- Python codec/schema: `tools/show_control_protocol.py`
- Browser codec: `web/show-pdu-codec.mjs`
- Runner: `tools/show_experience_runner.py`
- WebBridge/Launcher生成: `tools/recipe/show_runtime.py`
- JSON Schema: `schemas/show-control.schema.json`
