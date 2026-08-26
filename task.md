# hakoniwa-drone-show 開発タスク

## 目的

任意都市上で動作する既存のバーチャルドローンショーを、実際のドローンショーに
近い操作体験・演出計画・機体規模へ発展させる。

本書は、City World、MuJoCo Fleet、Map Viewerなどの基盤を構築した
[`hakoniwa-business-pack/task-virtual-drone-show.md`](https://github.com/hakoniwalab/hakoniwa-business-pack/blob/main/task-virtual-drone-show.md)
の後続タスクを管理する。
既存文書の風環境タスクやCity World基盤タスクは本書へ重複記載しない。

目標とする利用者体験は次のとおり。

```text
Launcherでruntimeを起動
  -> ブラウザを表示すると自動接続
  -> 都市、全Drone、観客視点を確認
  -> 「ドローンショー開始」を押す
  -> 計画された位置・色・明るさ・周期・タイミングで演出
  -> 既存バイナリの上限である256機まで同じ手順で実行
```

## 方針

- 今後追加するドローンショー固有機能は、原則として本リポジトリを正本とする
- Business Packには汎用Recipe基盤、City World生成、配布・納品統合だけを置く
- PRO環境を前提とするドローンショー専用Recipe、experiment、素材、テストは本リポジトリへ置く
- Viewer、Drone PRO、Three.js Drone、envsim固有実装は各Ownerへ置き、接続仕様を本リポジトリで管理する
- Business Packへショー固有ロジックやOwner実装を複製しない
- まず操作上の問題を解決し、その後に演出機能と機体数を拡張する
- ショー開始前に利用者がブラウザと構図を準備できるようにする
- LEDをViewer固有の装飾ではなく、ショー計画に含まれる状態として扱う
- 機体ごとのLED状態をPDUで送らず、Viewerも同じショー計画を解釈する
- ショー全体の現在フェーズだけを、任意有効化できる低頻度のJSON PDUで通知する
- 位置、LED、時間をShow Statusのシミュレーション時刻で同期する
- `show.json`をオフライン検証とruntime実行の共通入力にする
- Formation原画、点群化、機体割当、移動経路を分離し、生成過程を再現可能にする
- runtimeで場当たり的に割り当てず、遷移計画を原則オフラインで解決・検証する
- Viewerには回転、傾斜、スケール、機体数を反映したresolved show planを公開する
- 一般配布版とDrone PROのcapacity contractを混同しない
- Core、Drone、VSP、Foundationの再ビルドは行わない
- 手元の既存Drone PRO/Core PROバイナリで確認済みの256機を上限とする
- White Crowの300機事例は演出の参考とし、同一内容や素材の複製は行わない
- ICRA Recipe、ICRA測定用Runner、Drone PROの既存Show Runnerを変更しない
- Show開始待機とフェーズ通知は本リポジトリのShow Experience Runnerで追加する

## 完了の定義

- ブラウザ表示時に自動接続し、ショー開始前の全機を確認できる
- 利用者が開始ボタンを押すまでショーが始まらない
- 位置、LED色、明るさ、点灯効果、周期、タイミングをショー計画で指定できる
- 複数ブラウザや再実行でも、LEDがViewerのローカル時刻ではなくシミュレーション時刻に同期する
- Visual State PDUを変更せず、Show Statusはショー全体で1つのJSON PDUだけを使用する
- 200機で演出内容を安定化した後、同じ操作フローで256機を実行できる
- 256機で複数モチーフと複数色を使ったデモをブラウザから冒頭を含めて鑑賞できる
- ChromeとSafariで基本操作と表示を確認できる
- 任意の単純な絵から200機または256機のFormationを再現可能に生成できる
- Formation間の移動距離、交差、最小機体間隔、速度を実行前に検証できる

## Task 0: Business Packからショー専用Recipeを移行

### 目的

Business Packで現在実行できているCityドローンショーを、機能、設定、生成物、
起動手順および表示結果を変えずに本リポジトリから再現する。

Task 0は純粋な移植と責務分離に限定する。開始ボタン、Show Status、LED拡張、
Formation authoring、Transition planning、256機対応などの新機能はTask 0へ混在させない。

### 不変条件

- ICRA Recipe、Performance Runner、性能測定experimentおよび測定結果形式を変更しない
- 汎用`drone-fleet-single-host`の既定動作と一般向けCLIを変更しない
- 移行前のBusiness Pack実装をbaselineとし、移行後の同等性が確認できるまで削除しない
- 移行先がBusiness Pack内部実装をコピーして独自改変する構造にしない
- 外部拡張pointはショー固有名を持たず、未使用時に挙動を変えない

### 対象

- `tools/recipe/drone_fleet_mujoco_city.py`
- `tools/recipe/test_drone_fleet_mujoco_city.py`
- `tools/recipe/virtual_drone_show.py`
- `recipes/experiments/virtual-drone-show-city.yaml`
- キャラクターFormation生成など、上記に含まれるショー固有処理
- `drone_fleet_single_host.py`内のMuJoCo Cityショー専用CLIと直接import

### 残すもの

- ICRAおよびFleet性能検証用の`drone-fleet-single-host`基盤
- 一般利用可能なFleet生成、Foundation、Launcherの共通処理
- PLATEAU City World生成Recipe
- Business Packの配布・納品統合

### 要件

- [x] 移行前revision、実行条件、CLI、主要生成物hash、Show Receiptをbaselineとして保存する
- [x] 移行前のCityショーを起動し、MuJoCoとブラウザ表示の確認結果を記録する
- [x] Business Packの汎用Recipeへowner非依存の外部operator契約を追加する
- [x] Business Packから`drone_fleet_mujoco_city`の直接importを削除する
- [x] 本リポジトリのoperatorがBusiness Packの汎用Recipe基盤を呼び出す
- [x] City配置、共有MuJoCo model、Map Viewer設定を本リポジトリ側で構成する
- [x] 兄弟ディレクトリを既定とし、submoduleを使用しない
- [x] Business Pack、Drone PRO、ViewerのpathをCLIまたは設定で上書き可能にする
- [x] 既存のCityショーデモと同じ生成物を再現する移行テストを用意する
- [x] Business PackのICRA／性能検証テストに差分がないことを確認する
- [x] ICRA／性能測定のresolved experiment、Launcher、Runner引数、結果schemaに差分がないことを確認する
- [x] Business Pack側の旧CLIには移行先を示す明確な診断を設ける
- [x] 移行完了後、Business Packからショー固有コード、experiment、テストを削除する

### 実施順序

1. 移行前のbaselineと再現手順を固定する
2. 本リポジトリへショー固有コード、experiment、テストを移す
3. Business Packへ未使用時no-opとなる汎用拡張pointを追加する
4. 本リポジトリから従来と同じCityショーをconfigure、doctor、start、stopする
5. 生成物、runtime、MuJoCo表示、ブラウザ表示をbaselineと比較する
6. Business PackのICRA／性能検証テストと代表experimentを再検証する
7. 全条件を満たした後だけBusiness Packの旧ショー固有経路を削除する

### Acceptance Test

- [x] 本リポジトリからCityドローンショーRecipeをconfigureできる
- [x] Launcher、MuJoCo、Map Viewer、Show Runnerを従来どおり起動・停止できる
- [x] 移行前と同じ機体数、3種類のFormation、移動時間、hold時間、City配置を再現できる
- [x] 移行前後の主要生成物hashが一致するか、差分理由が説明・承認されている
- [x] Business Pack単体の汎用Fleet Recipeが`hakoniwa-drone-show`を要求しない
- [x] ICRA／Fleet性能検証の既存テストが通る
- [x] ICRA／性能測定の生成物とRunner引数に意図しない差分がない
- [x] 移行前後のresolved experiment、機体数、City配置、show planが同等である

## Task 1: ブラウザ準備後のショー開始

### 要件

- [x] Launcher起動とショー実行開始を分離する
- [x] 本リポジトリにShow Experience Runnerを新規追加する
- [x] Drone PROの`AssetShowStateMachine`を継承し、機体制御を複製しない
- [x] `--wait-for-show-start`を指定した場合だけ開始待機を有効にする
- [x] Launcher起動後、Drone Service、VSP、WebBridge、HTTP serverを準備する
- [x] ショー実行系は開始指示を受けるまで待機する
- [x] 待機中も各loopで`hakopy.usleep()`を呼び、箱庭時刻を停止させない
- [x] command/statusを別の1024 byte raw PDU channelとして定義する
- [x] 既存WebBridgeの同一WebSocket portで双方向転送する
- [x] ページ表示時にWebSocketへ自動接続する
- [x] ショー専用HTMLを追加し、既存Viewer画面の`Connect` UIへ依存しない
- [x] Show Runnerが`waiting`かつ全機表示後に`ドローンショー開始`ボタンを有効化する
- [x] 接続中、初期化中、開始待ち、実行中、完了、失敗を画面上で区別する
- [x] `run_id`、show hash、sequenceで開始要求の二重送信と二重起動を防止する
- [x] Status heartbeatから、再読み込みしたブラウザが現在の実行状態を復元できるようにする
- [x] Launcherの`stop`対象である既存show-runner assetだけを差し替える
- [ ] 第三者カメラは専用presetとして再設計し、離陸前の機体群を見渡せるようにする
- [ ] camera preset適用後は飛行へ追従せず、ユーザーのカメラ操作を上書きしない

通信仕様は[`docs/show-control-protocol.md`](docs/show-control-protocol.md)を正本とする。

### Acceptance Test

- [ ] `start`後にブラウザを開いてもDroneが離陸しない
- [ ] 自動接続が成功し、全機の初期位置を確認できる
- [ ] 開始ボタンを押すと、離陸を含む冒頭からショーが始まる
- [ ] ボタンを連打してもショーは一度だけ開始される
- [ ] Chromeで正常に動作する
- [ ] Safariで正常に動作する

## Task 2: Formation制作とオフライン移動計画

### 現状と課題

- 現在のFormation生成は文字と個別に実装した単純図形が中心である
- 現在の`index`割当は点群の並び順に見栄えと移動距離が依存する
- 現在の`nearest`割当はDroneを順番に処理するgreedy方式であり、全体最適ではない
- 現在のShow RunnerはFormationの終点を指示し、演出用の経路そのものは計画しない
- `duration_sec`は主に到達待ち時間であり、速度・加速度を保証する軌道時間ではない

### Formation authoring要件

- [ ] 原画と、飛行に使う正規化済みFormation点群を別成果物として扱う
- [ ] 初期入力形式としてSVGのpath、circle、rectとgroupを扱う
- [ ] PNG等の輪郭抽出は将来拡張とし、初期実装の必須条件にしない
- [ ] 原画座標をCity World上の回転、傾斜、スケールから独立した正規座標で保持する
- [ ] 輪郭線および塗り領域から、指定機数ちょうどの点を生成する
- [ ] 点群の最小間隔と、輪郭・内部パーツへの配分を指定できるようにする
- [ ] 各点へ安定したpoint ID、group ID、既定LED roleを付与できるようにする
- [ ] 同じ入力と設定から同じ点群を生成するdeterministicな処理にする
- [ ] 入力素材の出典、ライセンス、hashと生成設定をShow Receiptから追跡可能にする
- [ ] 2Dプレビューと、観客視点を含む3Dプレビューを生成できるようにする

### Transition planning要件

- [ ] 前Formationの点群と次Formationの点群を入力に、機体と到達点の割当をオフライン生成する
- [ ] `index`と現在のgreedy `nearest`を比較用baselineとして残す
- [ ] 256機で実用的な全体最適割当（Hungarian法または同等手法）を追加候補とする
- [ ] 初期コストは総移動距離を基本とし、point groupとLED roleの連続性を考慮できるようにする
- [ ] 直線遷移の軌跡交差、最接近距離、最大速度を事前計算する
- [ ] 安全間隔を満たせない遷移をvalidation errorとしてstep番号付きで報告する
- [ ] 必要な遷移だけ、高度レーンまたは中間waypointを使って交差を回避できる設計にする
- [ ] waypoint列を平滑化し、最大速度・加速度・必要に応じてjerkを検証できるようにする
- [ ] City World境界、地形・建物とのclearanceを配置時validationへ接続できるようにする
- [ ] 割当とwaypointをresolved show planへ格納し、RunnerとViewerが同じ計画を参照する
- [ ] 計画結果へhashを付与し、実行時に原画・Formation・Transitionの組合せを照合する

### 段階導入

1. SVG等から点群を生成し、全体最適割当と直線遷移validationを行う
2. その結果を使い、既存のFormation終点指示で見栄えと移動量を評価する
3. 交差や最小間隔に問題が残るstepだけ中間waypointを生成する
4. waypoint実行は本リポジトリのShow Experience Runnerへ追加し、Drone PROの既存Runnerは変更しない

### Acceptance Test

- [ ] サンプルSVGから200点と256点のFormationを生成できる
- [ ] 輪郭、目などの内部パーツ、LED groupが3Dプレビューで識別できる
- [ ] 同じ入力を複数回処理した結果とhashが一致する
- [ ] 全体最適割当の総移動距離が`index` baseline以下になる
- [ ] 交差数、最小機体間隔、最大速度をstepごとにレポートできる
- [ ] 制約違反時に、問題の機体、時刻、位置、必要な修正条件を表示できる
- [ ] resolved show planをViewerで事前再生し、runtimeと同じ割当を確認できる

## Task 3: ショー計画フォーマットの拡張設計

### 要件

- [ ] 既存の`formation`、`duration_sec`、`hold_sec`との互換性を維持する
- [ ] LED色をRGBまたは`#RRGGBB`で指定できるようにする
- [ ] LED明るさを指定できるようにする
- [ ] `steady`、`blink`、`fade`を初期対応の点灯効果とする
- [ ] 点滅周期とduty ratioを指定できるようにする
- [ ] 色・明るさの遷移時間を指定できるようにする
- [ ] 全機共通、グループ単位、formation point単位の指定方法を定義する
- [ ] timelineを逐次時間で記述し、必要に応じて開始offsetを表現できるようにする
- [ ] 時刻、周期、色、明るさ、対象機体の静的validationを定義する
- [ ] 旧形式を読み込んだ場合の既定LED状態を定義する
- [ ] サンプル`show.json`とJSON Schemaまたは同等の検証仕様を作成する
- [ ] resolved show planを生成し、Business PackがViewerのHTTP rootへ配置できるようにする
- [ ] resolved show planへ内容を識別するhashを付与する

### 設計上の不変条件

- LED演出の基準時刻は箱庭シミュレーション時刻とする
- Viewerの`requestAnimationFrame`累積時間を演出の正本にしない
- formation pointとDrone IDの割当変更後も、意図した色配置を維持できる表現にする
- 位置計画とLED計画を別ファイルへ分散させる場合も、1つのShow Receiptから追跡可能にする

### Acceptance Test

- [ ] 赤、緑、黄、青、白を含むサンプル計画を表現できる
- [ ] 常灯、2秒周期点滅、3秒フェードを表現できる
- [ ] キャラクターの輪郭と内部パーツへ異なる色を割り当てられる
- [ ] 既存のLED指定なし`show.json`を読み込める

## Task 4: Show Experience RunnerとShow Status JSON PDU

### 要件

- [x] Show Experience Runnerを本リポジトリのPython packageへ追加する
- [x] 既存のPerformance Runnerと同様に、Drone PROのShow Runner moduleを動的に読み込む
- [x] `AssetShowStateMachine`を継承し、既存のphase進行と機体制御をそのまま利用する
- [ ] Task 1の最小Statusをphase情報付きStatusへ拡張する
- [x] 新しいIDLを追加せず、1024 byte固定長raw PDU内でUTF-8 JSONを転送する
- [x] Show Statusはショー全体で1チャンネルとし、機体ごとのPDUを追加しない
- [ ] `schema_version`、`show_sha256`、`run_id`、`state`、`phase_index`、`phase_kind`、`show_elapsed_sec`、`phase_elapsed_sec`、`simulation_time_usec`、`sequence`を定義する
- [x] `initializing`、`waiting`、`running`、`completed`、`failed`の最小状態を通知する
- [ ] phase開始・完了時に即時通知し、実行中は既定1Hzのheartbeatを通知する
- [x] `--show-status-heartbeat-hz`でheartbeat周期を変更できるようにする
- [x] 起動時に新しい`run_id`を書き、前回実行のcommand/statusを無効化する
- [x] WebBridgeでShow Statusの1チャンネルだけをViewerへ転送する
- [ ] Viewerが`show_sha256`をresolved show planと照合し、不一致を拒否する
- [ ] Status PDUを無効化した場合は、従来のShow Runnerと同じ挙動を維持する

### Acceptance Test

- [ ] ICRA RecipeとPerformance Runnerの生成物・実行経路が変更されない
- [ ] Drone PROとenvsimに変更がない
- [ ] 新しいIDLやネイティブバイナリの再生成なしでStatusを送受信できる
- [ ] phase切り替え時にViewerが同じ`phase_index`を認識する
- [ ] 実行中にViewerを再読み込みしても最新Statusから復帰できる
- [ ] Status無効時に既存のVirtual Drone Showを実行できる

## Task 5: resolved show planに基づくLED描画と同期

### 要件

- [ ] Viewerがresolved show planをHTTPで読み込む
- [ ] Show Statusの`phase_index`から現在のtimeline stepを選択する
- [ ] heartbeat間は`phase_elapsed_sec`とブラウザのmonotonic clockで表示時刻を補間する
- [ ] 次のStatus受信時にシミュレーション時刻との差を穏やかに補正する
- [ ] 計画に基づいて常灯、点滅、フェードを再生する
- [ ] 全機共通、グループ単位、formation point単位の色と明るさを描画する
- [ ] Three.jsの既存LED Spriteへ色と明るさを反映する
- [ ] PointLightを機体数分追加せず、既存の軽量Sprite方式を維持する
- [ ] 現在のViewer内固定青色・固定周期処理を互換fallbackへ限定する
- [ ] Drone位置と現在formationの一致度を計算し、Statusとの明らかな不一致を警告する
- [ ] Status PDUがない場合だけ、位置一致度と開始時刻による推定をfallbackとして利用する
- [ ] position推定だけでhold経過時間を決定しない
- [ ] 計画違反を表示前に検出し、利用者に該当stepを示す
- [ ] 実際の開始時刻、各step時刻、完了理由をexecution summaryへ記録する

### Acceptance Test

- [ ] 同一編隊の一部を赤、緑、黄で同時表示できる
- [ ] LED offの機体が消灯して見える
- [ ] 3つ以上のformationを異なる色で順番に再生できる
- [ ] 低速点滅から常灯、フェードへの切り替えを確認できる
- [ ] 3回実行してstep開始タイミングが許容誤差内で一致する
- [ ] ブラウザの再描画負荷が変化してもLED周期がずれない
- [ ] ChromeとSafariで同じ色・明るさになる
- [ ] 200機表示時にLED追加前と比較して著しいFPS低下がない

## Task 6: 既存バイナリによる256機対応

### 前提

- `hakoniwa-drone-pro/docs/fleets/performance-report.md`では256機まで動作確認済み
- `hakoniwa-core-pro`既定の`HAKO_SERVICE_CLIENT_MAX`は256
- 一般配布版の契約上限200機とDrone PROの確認済み上限256機を区別する
- `research-512`への切り替えや再ビルドは本タスクの対象外

### 要件

- [ ] Business PackがDrone PRO利用を証跡から識別できるようにする
- [ ] 一般配布版では従来どおり200機を超える設定を拒否する
- [ ] 対応する既存Drone PRO/Core PRO環境では256機を選択可能にする
- [ ] 既存バイナリのbuild limitsをdoctorで検証する
- [ ] PDU size、packet分割、`max_drones_per_packet`、Bridge設定を同期する
- [ ] process分割、asset数、service数が既存build limits内であることを検証する
- [ ] 200機と256機で同じショー計画を使用できるようにする
- [ ] 256機時のsim step、VSP、Bridge、ブラウザFPS、メモリを記録する

### Acceptance Test

- [ ] Core、Drone、VSP、Foundationを再ビルドせず256機を起動できる
- [ ] 256機すべてがViewerへ表示される
- [ ] 256機すべてがformation commandへ追従する
- [ ] 欠落PDU、破損PDU、異常終了がない
- [ ] 3回実行し、残留processとportがない

## Task 7: 実在ショーを参考にした256機デモ

### 参考

- White Crow「りんくうEXPO2026前夜祭」300機ドローンショー
  - https://wh-crow.co.jp/achievements/achievements-drone-show-izumisano-rinku2026/
- 参考要素は、地域キャラクター、飛行機、特産品、複数モチーフの切り替え、地域性のある演出

### 要件

- [ ] 既存キャラクター素材の権利を侵害しない独自モチーフを選定する
- [ ] 地域またはCity Worldに関連する3種類以上のモチーフを用意する
- [ ] 複数色を使い、輪郭と内部パーツを区別する
- [ ] 少なくとも1つは移動を伴うアニメーションにする
- [ ] モチーフ間を滑らかに遷移させる
- [ ] 観客視点で判別できる高度、向き、大きさを設定する
- [ ] 過度な点滅を避け、疲れにくい周期と明るさにする
- [ ] 200機で演出を調整してから256機へ展開する
- [ ] SNS動画向けのcamera presetを用意する

### Acceptance Test

- [ ] 256機で3種類以上の演出を完走する
- [ ] 冒頭から終了までブラウザで鑑賞・録画できる
- [ ] 色、形、遷移がChromeとSafariで同等に見える
- [ ] execution summaryと使用したShow Receiptを保存できる

## 実装順序と依存関係

後続タスクを先行実装しない。

```text
Task 1: ブラウザ準備後の開始
  -> Task 2: Formation制作・Transition計画
       -> Task 3: ショー計画仕様
            -> Task 4: Show Experience Runner・Status通知
                 -> Task 5: resolved planによるLED描画・同期
                      -> Task 6: 既存バイナリで256機化
                           -> Task 7: 256機デモ制作
```

Task 0のRecipe移行を先に完了し、それ以降のショー固有機能をBusiness Packへ追加しない。

Task 2のresolved plan表現とTask 3の仕様確定前にShow Status JSON schemaを固定しない。
Task 4ではLED状態をPDUへ追加せず、現在phaseだけを通知する。Task 5までは200機以下で
機能を固め、演出内容が安定してからTask 6で256機へ拡張する。

## Repository ownership

| 責務 | Owner候補 |
|---|---|
| ショー専用Recipe、experiment、Show Receipt、PRO環境選択 | `hakoniwa-drone-show` |
| 汎用Recipe基盤、City World生成、配布・納品統合 | `hakoniwa-business-pack` |
| Formation authoring、機体割当、Transition planning、事前検証 | `hakoniwa-drone-show` |
| LEDを含むshow schema、resolved show plan、validation | `hakoniwa-drone-show` |
| Show Experience Runner、開始待機、Status JSON PDU | `hakoniwa-drone-show` |
| 既存show schema、機体制御、Show Runner | `hakoniwa-drone-pro`（変更なし） |
| Core build limitsとmanifest検証 | `hakoniwa-core-pro` |
| Drone visual state生成 | `hakoniwa-drone-pro`のVSP（変更なし） |
| Show StatusのPDU型 | 既存`std_msgs/String`を再利用 |
| LED Sprite、色・明るさ描画 | `hakoniwa-threejs-drone` |
| 自動接続、開始ボタン、状態表示 | `hakoniwa-map-viewer` |
| City World、地形、風、環境作用 | `hakoniwa-envsim`（変更なし） |

具体的な変更先は各Taskの調査で確定する。Business Packへowner repositoryの
実装を複製せず、Recipe側には設定生成と統合だけを置く。

## 非目標

- 300機以上への対応
- `research-512`プロファイルのビルド
- Visual State PDUへのLED、phase、時刻フィールド追加
- 機体ごとのLED状態PDU
- ICRA RecipeとICRA性能測定コードの変更
- Drone PROの既存Show Runnerの変更
- envsimへのショー進行管理の追加
- 実機DroneへのLED指令
- 実機運航、航空法、安全管理、飛行許可の再現
- 音楽・花火・レーザー同期の初期実装
- 実在キャラクター、ロゴ、第三者素材の無許諾利用
- runtimeでの動的なDrone同士の衝突回避や空力干渉
- 任意画像を自動で高品質な演出へ変換する汎用AI制作機能
- City WorldやMuJoCo基盤の再実装

## 進捗

- [x] Task 0: Business Packからショー専用Recipeを移行
- [ ] Task 1: ブラウザ準備後のショー開始
- [ ] Task 2: Formation制作とオフライン移動計画
- [ ] Task 3: ショー計画フォーマットの拡張設計
- [ ] Task 4: Show Experience RunnerとShow Status JSON PDU
- [ ] Task 5: resolved show planに基づくLED描画と同期
- [ ] Task 6: 既存バイナリによる256機対応
- [ ] Task 7: 実在ショーを参考にした256機デモ
