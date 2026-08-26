# Task 0 移行baseline

## 目的

Task 0の前後で、Cityドローンショーの入力、解決済み設定および主要生成物が変わって
いないことを確認するための再現証跡です。新しい開始待機、LED、Formation制作機能は
このbaselineへ含めません。

## 移行元

- Repository: `hakoniwa-business-pack`
- Revision: `faf7aefb150489257cab0cd8b7ee9276d212c1df`
- 旧operator: `tools/recipe/drone_fleet_single_host.py`
- 旧experiment: `recipes/experiments/drone-fleet-single-host-mujoco-city-2.yaml`
- Recipe workspace: `work/recipes/drone-fleet-single-host/`

移行元の追跡済みexperimentは2機用の最小設定でした。実際に表示確認したShizuoka
Cityデモではconfigure overrideを反映した解決済み設定をbaselineとします。

## Shizuoka City baseline

- City job: `shizuoka-22203-lat35.099-lon138.859`
- Drone count: 128
- Process count: 6
- Drones per process: 22
- Altitude mode: `city-max-clearance`
- Resolved flight altitude: `115.7100830078125 m`
- Formation rotation: `90 deg`
- Formation tilt: `15 deg`
- Show phases: `CHIIKAWA -> HACHIWARE -> USAGI`
- Final behavior: manual stopまで最後のFormationを保持

入力City Worldは次のreceiptです。

```text
hakoniwa-business-pack/work/remote-operation/city-world-worker/jobs/
  shizuoka-22203-lat35.099-lon138.859/build/world/city-world-receipt.json
```

## 移行先の再現command

```bash
cd hakoniwa-drone-show

python3 tools/recipe/virtual_drone_show.py configure \
  --mujoco-city-world \
  ../hakoniwa-business-pack/work/remote-operation/city-world-worker/jobs/shizuoka-22203-lat35.099-lon138.859/build/world/city-world-receipt.json \
  --altitude-mode city-max-clearance

python3 tools/recipe/virtual_drone_show.py doctor
python3 tools/recipe/virtual_drone_show.py start
python3 tools/recipe/virtual_drone_show.py status
python3 tools/recipe/virtual_drone_show.py stop
```

## 主要生成物hash

2026-08-26の移行前baselineと移行後configure結果は、次のSHA-256が一致しました。

| 生成物 | SHA-256 |
|---|---|
| `config/mujoco-city-fleet.json` | `59bad373a1d73b8da7ec62127ad59c2008de668290625024e6b85719af7ab4e4` |
| `config/resolved-experiment.yaml` | `1ca5fa5125716261b9ebe576f3116fe63141036f0c4a3b76408d7e13e921fe98` |
| `config/scenario/show.json` | `0f5bbf4c6328a847ab6737ec32e6558bf6308183a3e0ca6fcc37ca769526c8c6` |
| `config/drone/mujoco-city-fleet/receipt.json` | `3a48c57b3904160696c3f3308c1a378c5480e8285d816ba0ae6e85860058535d` |

絶対pathを含むため、別のworkspaceへ配置した場合のhash一致は要件としません。その場合は
resolved値、機体数、process分割、Formation、City component hashを比較します。

## 2026-08-26 移行後確認

- 移行前のMuJoCo／ブラウザ表示: 2026-08-25に目視確認済み
- City configure: PASS
- 128機、6 process model生成: PASS
- `doctor`: PASS
- 全6 MJBのMuJoCo reload: PASS
- Launcher `start/status/stop`: PASS
- Map Viewer HTTP response: PASS (`200`)
- Show Runnerの128機service登録: PASS
- 128機すべてのTakeOff完了response: PASS
- 停止後の残留process: なし
- 移行前後の主要生成物hash: 一致

初回実行時にHakoniwa Coreのmaster lock競合warningと、WebBridge monitor側の一時的な
`mux open error=8`を観測しました。Launcher、各Drone Service、Show Runner、Visual
State Publisher、WebBridge、HTTP serverは起動し、停止処理も完了しています。この
warningは移行生成物の差分ではありません。クリーン停止後の再実行では128機すべての
TakeOff完了responseを確認し、再停止後の残留processもありませんでした。
