# Global Wind PDU疎通テスト

Manual Wind UIから既存Web PDU Bridgeを経由して箱庭SHMへGlobal Wind JSONを送り、
Global Wind Assetが各DroneのDisturbance PDUへ展開することを確認する統合テストです。

```text
Browser Manual Wind UI
  -> hakoniwa-pdu-javascript
  -> Web PDU Bridge (:8765)
  -> DroneShow/global_wind_command (channel 2, 1024 bytes)
  -> SHM callback
  -> Global Wind Asset
  -> Drone-1..N/disturb
```

Show Controlと同じ`DroneShow`ロボットに、独立した一方向チャネルを追加しています。
テスト専用WebSocketサーバーや追加ポートは使用しません。

## 実行

通常のVirtual Drone Showと同じ手順です。

```bash
cd hakoniwa-drone-show
python tools/recipe/virtual_drone_show.py configure
python tools/recipe/virtual_drone_show.py start
python tools/recipe/virtual_drone_show.py open-viewer
```

ブラウザ左パネルの「風を操作」を開きます。

1. 「風を有効にする」をONにする
2. コンパスをドラッグして、風を流したい方角を指定する
3. 風速を変更する
4. 画面に`送信済み #N`と表示されることを確認する
5. 風向の数値欄で同じ値を再確定し、`変更なし（未送信）`になることを確認する
6. 風をOFFにしてzero vectorを送信する

Launcherが起動した`global-wind-asset`のログには、初期化とSHM callbackの処理結果が出ます。

```text
[GLOBAL_WIND] SHM callback ready
[GLOBAL_WIND] changed enabled=true vector_ros_m_s=[...] drones=200 elapsed_msec=...
```

ログファイル名と場所は生成済みLauncher設定で確認できます。起動時とreset時に1回、または
受信した物理状態が変わったときだけ、Global Wind Assetが全DroneへDisturbanceをfan-outします。
通常の20 msループでは`hakopy.usleep()`だけを実行します。

## Wire format

PDUはShow Controlと同様の固定長frameです。

- frame size: 1024 bytes
- magic: `HDW1`
- header: magic 4 bytes + JSON length 2 bytes + flags 2 bytes
- payload: UTF-8 JSON
- remaining bytes: zero padding

物理入力の正本は`wind.enabled`と`wind.vector_ros_m_s`です。手動操作のコンパスは
「風がその方角へ流れる」を表し、ブラウザでDisturbance PDUのROS座標へ変換してから送信します。
例えばNは北向き、Eは東向きの流れです。気象データの風向（from）を利用する場合は、送信前に
流れる方向（to）へ反転します。
Global Wind Assetはこの値を座標変換せず各DroneのPDUへコピーし、ROSからNEDへの変換は
既存のDrone PRO内部処理へ委ねます。
