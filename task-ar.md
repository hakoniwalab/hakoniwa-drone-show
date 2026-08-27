# AR Site Preview

## 目的

既存のShow File、Show IR、Show Status、Visual State PDUを再利用し、現実の風景へ
DroneとLEDだけを重畳するARサイトプレビューを実現する。PLATEAUおよびMuJoCo都市
モデルを必要とせず、会場での見え方確認、顧客提案、一般客向け体験へ発展できる
`hakoniwa-drone-show`固有機能として管理する。

初期PoCでは現在のPDU送信周期とruntime構造を維持する。一般客向けの低頻度配信と
ブラウザ補間は将来拡張とし、初期実装へ混在させない。

## 利用イメージ

```text
Show File / SVG
       ↓ configure
Show IR + 平面MuJoCo World
       ↓
現行Show Runner / PDU Bridge
       ↓
カメラ重畳AR専用Web UI
       ↓
カメラ映像 + Drone GLB + LED
```

City版とAR版は同じShow Fileを使用できる。

```text
                    ┌─ City Runtime: PLATEAU + MuJoCo都市 + Three.js
Show File / Show IR ┤
                    └─ AR Runtime: 平面World + Camera Overlay + Drone/LED
```

## リポジトリ境界

### `hakoniwa-drone-show`

- AR専用HTML、UI、カメラ重畳表示
- AR用Recipeおよびexperiment
- Show IR、Show Status、Visual State PDUとの接続
- 会場位置、仮想観客位置、方位、縮尺、高度の設定
- 初回GPS、テスト位置、会場方位とAR座標変換
- AR設定Schema、validation、テスト、利用手順

### `hakoniwa-threejs-drone`

- 既存のDrone GLBおよびLED Spriteを再利用する
- 追加が必要な場合も、汎用的な最小公開APIに限定する
- WebXR固有の画面やDrone Show固有設定は置かない

### `hakoniwa-business-pack`

- AR機能のコードおよびRecipeを追加しない
- 既存City版とICRA実行経路を変更しない

## 設計上の不変条件

- AR版はPLATEAU、City World Receipt、都市GLBを要求しない
- MuJoCo WorldはgroundとDroneを基本とし、都市meshと都市colliderを含めない
- Droneの位置は現行Visual State PDUを正本とする
- LEDは現行Show IRとShow Statusの`show_frame_index`へ同期する
- 初期PoCではPDU定義、チャネル数、送信周期を変更しない
- AR機能は専用ページで追加し、既存Viewerをデグレさせない
- GPSは初期位置計算時だけ取得し、継続追跡しない
- 初期位置決定後の観客移動はアプリ内の仮想ENU移動とする
- 端末姿勢は位置を変更せず、任意でyaw/pitchへ加算する
- 緯度経度だけでAR空間の床や方位が確定するとは扱わない
- AR表示は演出・視認性確認用であり、実機運航の安全証明とは扱わない

## 位置と座標

### 会場位置

`venue`は実際にショーを配置したい会場の基準位置を表す。

```yaml
ar:
  venue:
    latitude: 34.9717
    longitude: 138.3888
    heading_deg: 120.0
```

Show IRのENU座標は、会場原点と`heading_deg`を使ってARローカル座標へ変換する。
Show IRの高度は地面基準として扱い、GPS高度へ直接依存させない。

### 観客位置

ARアプリは次の位置情報源を切り替えられるようにする。

- `device`: 端末のGeolocationを使用する
- `override`: UIまたは設定で指定した仮想緯度経度を使用する

```yaml
ar:
  preview:
    location_source: override
    latitude: 34.9715
    longitude: 138.3886
    heading_deg: 120.0
```

これにより、例えば福井にいる開発者が静岡会場付近の観客位置を仮想的に指定して
配置計算を確認できる。`override`は端末GPSを書き換える機能ではなく、ARアプリ内の
座標計算へ注入するテスト用位置情報である。

### AR原点

初期PoCでは会場と観客の緯度経度差を地理ENUへ変換し、`venue.heading_deg`でShow ENUへ
対応付ける。観客のUpは平面床と`eye_height_m`から決定する。地面Hit Testや歩行追跡は
行わず、位置はYAMLの初期設定を維持する。yaw/pitchは任意の端末姿勢を利用し、編隊の
方向と距離は画面上のガイドで案内する。

## 段階的な実装方針

完成形を一度に作らず、現在動作しているCity版から一要素ずつ変更する。各段階で前段と
同じDrone位置、LED、開始操作になることを確認してから次へ進む。

```text
AR-0: 現行City Viewerをスマホから表示
  ↓
AR-1: iPhone/Android共通のカメラ重畳ARページ
  ↓
AR-2: 初回GPS + 任意の端末姿勢 + 編隊方向ガイド
  ↓
AR-3: HTTPS/WSSでiPhone実機確認
  ↓
AR-4: 必要に応じてAndroid WebXRを追加
```

## Task AR-0: 現行Viewerのスマホ表示

### 実装

- [x] 現行の静的WebサーバーをLANから接続可能なaddressへbindする
- [x] Viewer URLの`127.0.0.1`固定部分を、スマホから到達可能なホストへ置換する
- [x] WebSocket接続先へYAMLで指定したLANホストを反映する
- [x] MacのLAN IPを含むスマホ向けURLを`open-viewer`相当の操作で表示する
- [x] configureでスマホ向けURLのQRコードを生成する
- [x] LAN上のHTTPでもShow IRのSHA-256を検証できるfallbackを追加する
- [x] スマートフォンの観客視点で1本指yaw/pitch・ピンチFOVを操作できるようにする
- [x] AR鑑賞を妨げないよう、常設パネルを廃止し、仮想移動だけを小さな開閉ボタンへ収める
- [x] この段階ではCity World、PLATEAU、Viewer UI、PDU周期を変更しない

### Acceptance Test

- [ ] Macと同一LAN上のスマホから現行City Viewerを開ける
- [ ] スマホで180機、role別LED、ショー開始操作を確認できる
- [ ] Mac上の従来URLでも同じViewerを利用できる

## Task AR-0.5: PLATEAUなしの平面Runtime

### 実装

- [x] `environment.mode`で`plateau`と`flat`を切り替えられるようにする
- [x] `flat`でCity World Receiptを不要にする
- [x] 指定したローカルZへ平面床を置いた軽量MuJoCo fleet modelを生成する
- [x] 機体中心を床から既定0.20m上へ配置する
- [x] `scenario.altitude_m`を床からのAGLとしてShow IRへ反映する
- [x] 都市GLBを含まないThree.js sceneを生成する
- [x] City版と同じShow File、Show Runner、PDU、LED、Viewer UIを再利用する

### Acceptance Test

- [ ] `flat`を180機・8プロセスでconfigureできる
- [ ] 生成MuJoCo modelに都市mesh/colliderが含まれず、平面床だけが存在する
- [ ] 機体が指定した床面から離陸し、5 Formationとrole別LEDを最後まで再生できる
- [ ] `plateau`へ戻した場合に従来City World構成を生成できる

## Task AR-1: 共通カメラ重畳AR

### 実装

- [x] WebXRへ依存しないiPhone/Android共通のAR専用ページを追加する
- [x] 背面カメラ映像を全面表示する
- [x] Three.js rendererとscene背景を透明化する汎用APIを追加する
- [x] 既存Viewerと同じruntime設定、Drone、LED、PDU接続をARページで再利用する
- [x] PLATEAU、Leaflet、都市GLBをARページから読み込まない
- [x] Show開始とShow Statusを既存PDU channelで再利用する

### Acceptance Test

- [ ] iPhone SafariでカメラARを開始・終了できる
- [ ] カメラ映像上で180機とrole別LEDを確認できる
- [ ] ARページと通常ViewerでDrone位置とLED状態が一致する
- [ ] カメラ権限拒否時に通常Viewerを壊さず、明確な案内を表示できる

## Task AR-2: 初回位置・端末姿勢・編隊方向ガイド

### 実装

- [x] `venue.latitude`、`venue.longitude`、`venue.heading_deg`を定義する
- [x] 起動時に端末GPSを一度だけ取得する
- [x] `device`失敗時は`override`へfallbackし、遠隔テストではYAMLで`override`を選べるようにする
- [x] 会場と観客の緯度経度差をローカルENUへ変換する
- [x] YAMLで決めた初期位置から、折りたたみ式ボタンで前後左右・上下へ仮想移動できる
- [x] `device_orientation: optional`ならAR開始操作から端末姿勢をyaw/pitchへ反映する
- [x] Visual Stateの全機実位置から編隊中心を求める
- [x] Visual State受信前はShow IRの編隊中心を方向案内に使用する
- [x] 視野外では画面端の矢印で編隊方向を表示し、視野内では中央マーカーを消す
- [x] 左上の距離ボタンで編隊中心までの距離を表示・非表示できる
- [x] 左下に初期位置基準の前後左右、地面からの高さ、最寄り機までの距離を表示する
- [x] 端末を上へ向ける操作とpitchを一致させ、遠距離ほど端末姿勢の手ぶれ補正を強くする

### Acceptance Test

- [ ] 実際の会場位置で端末GPSから初期観客位置を計算できる
- [ ] 福井から静岡の`override`位置を使って表示できる
- [ ] iPhoneを向けると方向矢印が視野内マーカーへ変わる
- [ ] 端末姿勢がyaw/pitchへ反映され、`off`設定では固定できる

## Task AR-3: iPhone向けHTTPS/WSS

### 実装

- [x] configureで再利用可能なローカルCAとIP SAN付き証明書を生成する
- [x] HTTPS `:8443`でAR静的ファイルを配信する
- [x] 同一オリジンのWSS `:8443/pdu`を既存WebBridge `ws://127.0.0.1:8765`へ中継する
- [x] 診断・互換用のWSS `:8766`も維持する
- [x] AR URL、QR、CA証明書、CA導入QRを生成する
- [x] CA秘密鍵とサーバー秘密鍵を生成workspaceだけに置く
- [x] iPhoneへのCA導入と信頼設定を文書化する

### Acceptance Test

- [ ] iPhone SafariからHTTPS AR URLを開ける
- [ ] 証明書信頼後にカメラとGeolocationを許可できる
- [ ] WSS経由で180機とShow Statusを受信できる
- [ ] 通常HTTP Viewerと既存`ws://8765`が継続して利用できる

## Task AR-4: Android WebXR（将来・任意）

### 実装

- [ ] `immersive-ar`のfeature detectionを追加する
- [ ] Android対応端末ではWebXR sessionへ切り替えられるようにする
- [ ] Camera OverlayとDrone/LED/PDUコードを共通利用する
- [ ] WebXR固有のHit Testと空間trackingが商品ユースケースに必要か再評価する

### Acceptance Test

- [ ] WebXR非対応時もCamera Overlay版が継続して動く
- [ ] WebXR追加前後でShow IR、PDU、LEDの結果が一致する

## Task AR-5: 商品化に向けた互換性

- [ ] Android、iPhone、タブレットの対象範囲を決定する
- [ ] WebXR非対応端末向けカメラ重畳fallbackの要否を判断する
- [ ] 端末性能別の最大Drone数とFPSを測定する
- [ ] GLB、LED Sprite、通信量、初回ロード時間を計測する
- [ ] 位置情報とカメラ権限の説明、同意、エラー導線を整備する
- [ ] 一般客へ配布するURLとShow IRのアクセス制御を設計する
- [ ] AR表示結果を安全検証へ流用しない旨を明記する

## 将来拡張: 一般客向け時刻同期

初期PoCには含めない。一般客へ多数配信する段階では、全機体状態の高頻度配信ではなく、
Show IRを初回配信し、0.5秒程度の間隔で同期情報を送る方式を候補とする。

```text
初回: Show IR + hash
定期: run_id + show_time + state
操作: START / PAUSE / SEEK
描画: ブラウザ内で位置・時刻を補間
```

- [ ] 2 Hz程度の同期通知で許容できる時刻誤差を定義する
- [ ] 通知間を端末時計で進め、補正時に位置やLEDを急変させない
- [ ] CDN配信したShow IRとruntimeのhash一致を検証する
- [ ] 再接続、バックグラウンド復帰、途中参加の同期規則を定義する
- [ ] 同時接続数とサーバー帯域を測定する

## 初期PoCで行わないこと

- PDU定義およびPDUチャネルの追加
- 現行RunnerとBridgeの送信周期変更
- GPSだけを用いたセンチメートル級の配置
- 複数端末間の高精度な共有アンカー
- 実機Droneへの指令
- 実機運航の衝突、安全、法令適合性の保証
- City版、Business Pack、ICRA資産の変更
