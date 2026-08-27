# PLATEAU City版からAR版への対応手順

## 目的

既存のPLATEAU City版ドローンショーを基準に、Show Runner、PDU通信、Show IR、LED同期を
維持したまま、スマートフォン向けカメラ重畳ARへ段階的に展開する手順を示します。

この手順の要点は、最初からPLATEAUを外さないことです。まず既存City版をスマートフォンで
再現し、次に描画背景だけをカメラへ差し替え、最後にMuJoCoとThree.jsから都市データを
取り除きます。各段階で直前の構成と比較できるため、表示、通信、座標変換のどこで問題が
生じたかを切り分けられます。

```text
PLATEAU City版（Macブラウザで動作確認済み）
  ↓ 1. 同じCity版をスマートフォンへ公開
PLATEAU City版（スマートフォン表示）
  ↓ 2. 透明Three.js + 背面カメラのARページを追加
PLATEAUを読み込まないAR描画（Runtimeは従来構成）
  ↓ 3. MuJoCo都市モデルを平面Worldへ交換
PLATEAUなしAR Runtime
  ↓ 4. GPS、端末姿勢、方向案内、立体感を追加
現在のARプレビュー
```

## 変更しない境界

AR対応中も、次の要素はCity版と共通のまま維持します。

- Show File、Formation、Show PlanおよびShow IR
- Show Experience RunnerとブラウザからのSTART制御
- Visual State PDUとShow Status PDU
- WebBridgeおよび既存PDUチャネル数
- Drone GLBとShow IRに解決済みのLED状態
- Fleet制御、箱庭時刻同期およびPDU送信周期

AR固有のHTML、設定、証明書生成、座標変換は`hakoniwa-drone-show`で管理します。
Three.js側へ必要な変更は、透明背景、観客カメラ、LED表現など、通常Viewerでも再利用可能な
最小APIに限定します。Business PackのCity版およびICRA経路へAR固有処理を追加しません。

## 事前条件: PLATEAU City版を基準化する

AR対応前に、Macの通常Viewerで次を確認します。

1. PLATEAU City Worldを使って`configure`できる。
2. 全機が表示され、ブラウザの開始操作まで待機する。
3. Show FileどおりにFormation、待機時間、LEDが切り替わる。
4. 正常な`stop`でLauncherと箱庭Runtimeを終了できる。

`recipes/experiments/virtual-drone-show-city.yaml`のRuntime種別をPLATEAUへ切り替えます。

```yaml
environment:
  mode: plateau
  plateau:
    city_world_receipt: ../../../hakoniwa-business-pack/work/remote-operation/city-world-worker/jobs/shizuoka-22203-lat35.099-lon138.859/build/world/city-world-receipt.json
    altitude_mode: route-clearance
```

```bash
python3 tools/recipe/virtual_drone_show.py configure
python3 tools/recipe/virtual_drone_show.py doctor
python3 tools/recipe/virtual_drone_show.py start
python3 tools/recipe/virtual_drone_show.py open-viewer
python3 tools/recipe/virtual_drone_show.py stop
```

この結果を基準にし、以降の各段階でDrone位置、LED、開始操作が一致することを確認します。

## 段階1: PLATEAU City版をスマートフォンへ公開する

都市モデルとViewerは変更せず、ネットワーク経路だけをLAN対応にします。

1. Macとスマートフォンを同じLANへ接続する。
2. `viewer.network.host`へMacのLAN IPを設定する。
3. 静的WebサーバーをLANから到達可能なaddressへbindする。
4. Viewer URLとWebSocket URLへLAN IPを反映する。
5. `configure`でURLとQRコードを生成する。
6. Macの通常URLとスマートフォンのQR URLの両方でCity版を確認する。

この段階ではPLATEAU、MuJoCo World、Viewer画面、PDU周期を変更しません。スマートフォンで
問題があれば、ARや座標変換ではなくHTTP/WebSocketの公開設定へ原因を限定できます。

生成物は次のとおりです。

```text
work/recipes/drone-fleet-single-host/viewer-access/
  viewer-url.txt
  viewer-qr.svg
```

## 段階2: カメラ重畳ARページを追加する

通常Viewerを残したまま、AR専用ページを追加します。

1. 背面カメラ映像をページ全面へ表示する。
2. Three.js rendererを透明背景で初期化する。
3. City環境、Leaflet、都市GLBをARページから読み込まない。
4. Drone GLB、LED、Visual State、Show Status、START制御は通常Viewerと同じ実装を使う。
5. 通常ViewerのHTTP `:8000` / WebSocket `:8765`を維持する。
6. iPhone用にHTTPS `:8443`と同一オリジンWSS `/pdu`を追加する。

WebXRは使用せず、カメラ映像と透明Three.jsを重ねる方式を先に採用します。これにより
iPhone SafariとAndroid Chromeで共通基盤を持ち、Android WebXRは必要性を確認してから
追加できます。

この段階の確認項目は次のとおりです。

- カメラ許可前でもページとエラー案内を表示できる。
- カメラ許可後に通常Viewerと同じ機体位置・LEDを表示する。
- ブラウザの開始ボタンから同じRunnerを開始できる。
- ARページの障害が通常Viewerへ影響しない。

## 段階3: PLATEAUを平面Runtimeへ置き換える

AR表示で実世界を背景に使えることを確認した後、シミュレーション側の都市データを外します。

```yaml
environment:
  mode: flat
  flat:
    ground_height_m: 5.479387621660862
    origin:
      latitude: 35.0988
      longitude: 138.8587
      altitude_offset_m: 2.7360082114794118
```

`flat`では次の軽量構成を生成します。

- 指定高度の平面床
- 床から既定0.50m上に配置したDrone
- City mesh、都市collider、City World Receiptを含まないMuJoCo model
- 都市GLBを含まないThree.js scene

`scenario.altitude_m`は床からの最低Formation高度（AGL）として扱います。離陸位置と高度を
PLATEAU版から比較し、床の高度差でShow全体が上下へずれていないことを確認します。

PLATEAU版へ戻す場合は`environment.mode: plateau`へ戻して再度`configure`します。
`environment.plateau`に固定したReceiptと高度解決方式が使われます。Show FileとARページは
共通なので変更しません。

## 段階4: 現地座標とAR鑑賞機能を追加する

軽量RuntimeがCity版と同じショーを再生できた後、AR固有の位置・姿勢機能を追加します。

1. 会場基準緯度経度と`heading_deg`を定義する。
2. 端末GPSまたは`override`から初期観客位置を一度だけ求める。
3. 会場との差を地理ENUへ変換し、Show ENUへ対応付ける。
4. 端末姿勢は位置ではなくyaw/pitchにだけ反映する。
5. 編隊中心への画面端矢印、距離、相対位置を表示する。
6. 必要時だけ仮想移動UIを開けるようにする。
7. Formationへ奥行きを付け、近距離では立体LED、遠距離ではLEDハローを強調する。

観客位置は初期設定を基本とし、GPSへ継続追従しません。観客席で鑑賞する用途では移動せず、
仮想移動は遠隔テストと配置調整のための補助操作として扱います。位置を動かしながら見ると
基準が分かりにくくなるため、通常のデモでは固定観客席を推奨します。

## 検証順序

問題の切り分けを容易にするため、次の順序で確認します。

1. Mac通常Viewer + PLATEAU
2. スマートフォン通常Viewer + PLATEAU
3. スマートフォンARページ + 従来Runtime
4. Mac通常Viewer + flat Runtime
5. スマートフォンARページ + flat Runtime
6. `override`位置 + 固定観客席
7. 端末GPS + 実際の会場

各段階で、全機数、開始待機、Show IR hash、Formation時刻、LED、正常停止を確認します。
一度にネットワーク、AR、PLATEAU除去、座標変換を変更しないことが重要です。

## 現在の制約

- カメラ重畳方式であり、iPhoneではWebXRの実空間Hit Testを使用しません。
- GPSは初期位置だけに使用し、センチメートル級の配置を保証しません。
- 端末姿勢の手ぶれ補正は表示上の処理であり、共有空間アンカーではありません。
- 仮想移動は端末GPSを変更せず、ARアプリ内の観客座標だけを変更します。
- AR表示は演出と視認性の確認用であり、実機運航の安全判断には使用できません。
- 一般客向け低頻度同期とブラウザ補間は未実装です。

## 2026-08-27時点の確認結果

次の構成は実機で確認済みです。

- iPhoneから生成QRコードを使ってHTTPS ARページを表示
- 同一オリジンWSS経由でVisual StateとShow Statusを受信
- PLATEAUを使わない`flat` Runtimeで180機のショーを表示
- `override`の仮想緯度経度を使い、会場外から会場付近の観客位置を再現
- カメラ映像上でShow開始、Formation遷移、role別LEDを表示
- 端末姿勢、編隊方向矢印、距離切替、相対位置、補助的な仮想移動を操作
- Formationの湾曲と距離適応LEDによる奥行き表現を確認
- 固定観客席を基本とし、必要な場合だけ仮想移動する運用を確認

実際の会場におけるGPS初期位置、端末・OS別性能、同時多数接続、Android WebXR、実機運航との
整合性は未確認です。

利用者向けの起動、証明書導入、設定および画面操作は
[カメラARプレビュー](ar-preview.md)を参照してください。要件と今後の作業は
[`task-ar.md`](../task-ar.md)を参照してください。
