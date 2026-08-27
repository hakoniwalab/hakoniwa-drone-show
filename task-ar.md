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
Show IR + 軽量MuJoCo World
       ↓
現行Show Runner / PDU Bridge
       ↓
AR専用Web UI
       ↓
カメラ映像 + Drone GLB + LED
```

City版とAR版は同じShow Fileを使用できる。

```text
                    ┌─ City Runtime: PLATEAU + MuJoCo都市 + Three.js
Show File / Show IR ┤
                    └─ AR Runtime: 軽量World + WebXR + Drone/LED
```

## リポジトリ境界

### `hakoniwa-drone-show`

- AR専用HTML、UI、WebXRセッション
- AR用Recipeおよびexperiment
- Show IR、Show Status、Visual State PDUとの接続
- 会場位置、仮想観客位置、方位、縮尺、高度の設定
- 地面への原点配置とAR座標変換
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
- AR機能は専用ページと専用Recipeで追加し、既存City Viewerをデグレさせない
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

初期PoCではWebXR Hit Testを使い、画面上で地面をタップしてAR原点を確定する。
緯度経度から求めた会場と観客の相対ENU位置を、そのローカル原点と手動または設定済み
方位へ対応付ける。

## 段階的な実装方針

完成形を一度に作らず、現在動作しているCity版から一要素ずつ変更する。各段階で前段と
同じDrone位置、LED、開始操作になることを確認してから次へ進む。

```text
AR-0: 現行City Viewerをスマホから表示
  ↓
AR-1: 同じ構成のARページを追加し、背景を透明化
  ↓
AR-2: ブラウザ側からPLATEAU、Leaflet、都市GLBを除去
  ↓
AR-3: MuJoCo側から都市mesh/colliderを除去
  ↓
AR-4: 会場位置、仮想観客位置、配置調整
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
- [x] PC・スマートフォン共通で、観客位置を固定できる移動操作OFFと前後左右・上下の半透明ボタンを追加する
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

## Task AR-1: 都市付き構成のAR化

### 実装

- [ ] AR対応状況を`immersive-ar`のfeature detectionで判定する
- [ ] Three.jsのARセッションを開始・終了できる最小ページを追加する
- [ ] 既存Viewerと同じruntime設定、Drone、LED、PDU接続をARページで再利用する
- [ ] rendererとscene背景をAR向けに透明化し、カメラ映像を背景として表示する
- [ ] この段階ではPLATEAU読込経路を残し、既存構成との差分をAR表示だけに限定する
- [ ] HTTPS Gatewayから静的ファイルを配信し、既存WebSocketをWSSで中継する
- [ ] HTTPSと証明書を含む端末確認手順を整理する
- [ ] WebXR非対応時に、対応端末・ブラウザが必要であることを画面表示する

### Acceptance Test

- [ ] 対応端末でARセッションを開始・終了できる
- [ ] カメラ映像上で180機とrole別LEDを確認できる
- [ ] ARページと従来City ViewerでDrone位置とLED状態が一致する
- [ ] 非対応ブラウザで通常Viewerを壊さず、明確な案内を表示できる

## Task AR-2: ブラウザ側PLATEAUの除去

### 実装

- [ ] AR専用ページを追加し、PLATEAU、Leaflet、都市GLBを読み込まない
- [ ] Drone GLB、LED、Show UI、WebSocket/PDU接続だけを残す
- [ ] City版とAR版のruntime設定を分け、City版の生成物を変更しない

### Acceptance Test

- [ ] PLATEAU、Leaflet、都市GLBへのHTTP requestが発生しない
- [ ] 都市描画を外した前後でDrone位置、時間、role別LEDが一致する
- [ ] 現実のカメラ背景、Drone、LED以外の都市描画が表示されない

## Task AR-3: MuJoCo都市データの除去

### 実装

- [ ] groundとDroneを基本とする軽量MuJoCo Worldを生成するAR用Recipeを追加する
- [ ] AR版configureからCity World Receipt依存を外す
- [ ] City版と同じShow FileをAR版でも選択できるようにする

### Acceptance Test

- [ ] AR版のconfigureと起動にCity World Receiptが不要である
- [ ] MuJoCo runtimeへ都市meshおよび都市colliderが含まれない
- [ ] 180機の子供向けショーをAR表示できる
- [ ] ネコからAIロボットまで位置、時間、role別LEDがCity版と一致する
- [ ] 既存City版と旧Viewerのテストが継続して成功する

## Task AR-4: 会場配置と仮想位置

### 実装

- [ ] `venue.latitude`、`venue.longitude`、`venue.heading_deg`を定義する
- [ ] 観客位置の`device`と`override`を切り替えられるようにする
- [ ] UIで仮想緯度経度と方位を変更できるようにする
- [ ] 会場と観客の緯度経度差をローカルENUへ変換する
- [ ] Hit Testによる地面タップでAR原点を確定する
- [ ] scale、heading、show altitudeをAR画面で微調整できるようにする
- [ ] 調整値をYAML形式でコピーできるようにする
- [ ] 最後に使用したpreview設定を端末ローカルへ保存できるようにする

### Acceptance Test

- [ ] 福井から静岡会場の仮想観客位置を指定してプレビューできる
- [ ] `device`と`override`で同じ座標を指定した場合に同じ配置結果となる
- [ ] 観客位置を東西南北へ動かすと、会場の相対方向が正しく変化する
- [ ] 方位と縮尺を変更してもShow IR自体は変更されない

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
