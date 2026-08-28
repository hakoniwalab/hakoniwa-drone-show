# Cityドローンショー設定

`recipes/experiments/virtual-drone-show-city.yaml`は、PLATEAU City Worldまたは
平面World上で実行するVirtual Drone Showの既定experimentです。この文書は設定項目の正本です。

設定を変更した場合は、生成済みShow IRやLauncherへ自動反映されません。Launcherを
正規終了してから`configure`を再実行してください。

```bash
python3 tools/recipe/virtual_drone_show.py stop
python3 tools/recipe/virtual_drone_show.py status

# statusがTERMINATEDであることを確認する（flat mode）
python3 tools/recipe/virtual_drone_show.py configure

# plateau modeではenvironment.plateauの設定を使用する
python3 tools/recipe/virtual_drone_show.py configure
```

## Formationの大きさ

`scenario.formation.scale_m`は、SVGから作られた正規化Formationを実空間へ展開した
ときの公称最大寸法です。元Formationの幅・高さ・奥行きの最大spanが`scale_m`メートルに
なるよう、全軸へ同じ倍率を適用します。縦横比は変わりません。

```yaml
scenario:
  formation:
    scale_m: 15.33125
    depth_m: 3.0
```

この値を小さくすると顔全体が小さくなり、大きくすると拡大します。現在の
`15.33125 m`は、移行前の約`61.325 m`に対して厳密に1/4の大きさです。
`--formation-scale 20`を`configure`へ渡すと、その実行に限りYAMLの値を`20 m`で
上書きできます。

`scale_m`はFormationの向き（yaw/tilt）を適用する前の公称寸法です。向きを変えた後の
ENU各軸のaxis-aligned bounding boxは、回転によってこの値より小さく見える場合が
あります。

`depth_m`は、正面シルエットを保ったままFormationを観客側へ湾曲させる最大奥行きです。
左右端は元の平面上に残り、横方向の中央ほど最大`depth_m`だけ手前へ出ます。`0`なら
従来どおり完全な平面です。値は`0`以上`scale_m`以下にします。

## 全設定項目

### ルート

| 項目 | 型・制約 | 説明 |
|---|---|---|
| `version` | 整数、現在は`1` | experiment設定形式のバージョンです。 |

### `experiment`

| 項目 | 型・制約 | 説明 |
|---|---|---|
| `experiment.id` | 空でない文字列 | experimentと生成結果を識別するIDです。通常は変更しません。 |

### `scale`

| 項目 | 型・制約 | 説明 |
|---|---|---|
| `scale.drone_count` | 1以上の整数 | ショー全体の機体数です。Formationもこの機体数へ再サンプリングされます。現在の一般ユーザー向け上限は128機です。`configure --drone-count`で一時上書きできます。 |
| `scale.process_count` | 1以上かつ機体数以下の整数 | Drone Serviceのプロセス数です。機体は全プロセスへ均等に自動分割されます。`drones_per_process`は指定しません。`configure --process-count`で一時上書きできます。 |

### `scenario.launch_area`

`scenario.launch_area`は、ショーのFormation位置を変えずに、離陸時の初期配置だけを
別の場所へ移す設定です。座標はDrone PDUと同じROSローカル座標系で、ショー中心を
原点とするメートル値です。

```yaml
scenario:
  launch_area:
    mode: auto
    search_radius_m: 80.0
```

`auto`は機体を碁盤状に収める矩形領域を作り、ショー中心から`search_radius_m`以内で
領域全体が
平坦な場所を探索します。領域は前後左右に3mの安全余白を持ち、1m間隔で地面と建物を
検査します。領域全体の標高差は5cm以内、各機の接地範囲内は5mm以内でなければ採用
しません。これはCity Worldデータを用いるベストエフォート探索です。必要な大きさの
単一領域を確保できない場合、`configure`はエラーで終了します。

離陸場所を明示したい場合は`manual`を使います。

```yaml
scenario:
  launch_area:
    mode: manual
    offset_m: [20.0, -30.0, 0.0]
```

`offset_m`は`[x, y, z]`です。`x`と`y`は飛行場所（ショー中心）から離陸領域の
中心までの相対距離です。`z`は、その場所で検出した地表面から追加する高さで、
通常の地上離陸は`0.0`にします。`manual`では指定位置を信頼して碁盤配置をそのまま置き、
平坦性や建物との重なりによるconfigureエラーにはしません。各機の初期高度だけは指定地点の
地表またはコライダー上面から解決します。City World範囲外の場合のみエラーになります。
Formation、Show IR、
観客カメラ、照明の座標はこの設定では移動しません。

| 項目 | 型・制約 | 説明 |
|---|---|---|
| `scenario.launch_area.mode` | `auto`または`manual` | 初期配置場所の決定方式です。 |
| `scenario.launch_area.search_radius_m` | `auto`時のみ、0〜500 | ショー中心から平坦領域を探索する最大半径（m）です。小さいほどconfigureは速く、候補がなければエラーになります。 |
| `scenario.launch_area.offset_m` | `manual`時のみ必須、3要素の有限数配列 | ショー中心からの相対`[x, y, z]`（m）です。`z`は0〜100mです。 |

### `runtime`

| 項目 | 型・制約 | 説明 |
|---|---|---|
| `runtime.mode` | 現在は`native` | ホスト上で動かすruntime方式です。 |
| `runtime.visualization` | 真偽値 | VSP、WebBridge、HTTP ViewerをLauncherへ含めます。ブラウザ開始型のShowでは`true`が必須です。 |
| `runtime.show_runner_real_time_sync` | 真偽値 | Show Runnerの進行をwall-clock時間へ同期します。観賞用Showでは通常`true`にします。 |

### `global_wind`

| 項目 | 型・制約 | 説明 |
|---|---|---|
| `global_wind.enabled` | 真偽値 | Global Wind Assetとブラウザ風操作を有効にします。 |
| `global_wind.initial_mode` | `manual`または`live` | Viewer起動時の風入力モードです。 |
| `global_wind.manual.enabled` | 真偽値 | Manualモードの初期風有効状態です。 |
| `global_wind.manual.speed_m_s` | 0〜30 | Manualモードの初期平均風速です。 |
| `global_wind.manual.direction_to_deg` | 0〜359 | 風が実際に流れる方位です。0°=北、90°=東です。 |
| `global_wind.manual.speed_stddev_m_s` | 0〜15 | 機体ごとの風速標準偏差です。0なら全機同速です。 |
| `global_wind.live.provider` | `open-meteo` | Live weather providerです。 |
| `global_wind.live.poll_interval_sec` | 60〜86400 | 自動取得間隔です。既定は300秒です。 |
| `global_wind.live.timeout_sec` | 1〜30 | HTTP取得timeoutです。 |
| `global_wind.live.stale_after_sec` | poll間隔以上86400以下 | 最終成功値をSTALE表示へ切り替える時間です。 |
| `global_wind.scenario.enabled` | 真偽値 | 再現可能なWind Scenarioを箱庭時刻で再生します。 |
| `global_wind.scenario.file` | experimentからの相対パスまたは絶対パス | Wind Scenario v1 JSONです。相対パスはexperiment YAML基準です。 |

Liveモードでは、会場座標をPLATEAU City Worldのorigin（flatではflat origin）から
`configure`時に解決します。Open-Meteoの気象風向（from）を、実際に流れる方向（to）へ
自動変換してコンパスへ表示します。平均風速と方向はprovider値ですが、標準偏差はブラウザで
引き続き調整できます。`最新値を取得`は5分間隔を待たず即時取得し、同じ物理値ならPDUを
再送しません。`Open-Meteoで確認`は、その取得に使うAPI URLを別タブで開きます。

Scenarioを有効にすると、ブラウザのManual／Live入力はGlobal Wind Asset側で無視されます。
イベントはShow IRの離陸完了を0秒とする`show_time_usec`に従い、既定約250 msの時刻通知で
進行します。ブラウザは同じScenario JSONと`show_time_usec`から現在イベントを解決し、風向、
平均風速、標準偏差をコンパスへ表示します。サンプルは
`examples/wind-scenarios/osaka-gust-east.json`です。Manual／Liveへ
戻す場合は`global_wind.scenario.enabled: false`にして、再度`configure`してください。

衝突評価はtakeoff完了直後のカウンタをbaselineとして保存し、Scenarioの最終イベントから
10秒後にfinalを取得して`validation/execution-summary.json`へ出力します。最後のFormationを
表示し続ける時間とは独立しているため、評価結果のために表示保持の終了を待つ必要はありません。

### `environment`

| 項目 | 型・制約 | 説明 |
|---|---|---|
| `environment.mode` | `plateau`または`flat` | `plateau`はCity World Receiptの都市mesh・terrain・colliderをMuJoCoとViewerへ組み込みます。`flat`は都市データを一切使わず、Droneと平面床だけの軽量MuJoCo Worldを生成します。 |
| `environment.plateau.city_world_receipt` | experimentからの相対パスまたは絶対パス | `plateau`で使用するBusiness PackのCity World Receiptです。相対パスはexperiment YAMLのディレクトリを基準に解決します。`--mujoco-city-world`はこの値を一時上書きします。 |
| `environment.plateau.altitude_mode` | `route-clearance`または`city-max-clearance` | 飛行高度の解決方式です。`route-clearance`は離陸領域とFormation各点の周辺にある最高コライダー、`city-max-clearance`はCity全体の最高コライダーを基準にします。`--altitude-mode`はこの値を一時上書きします。 |
| `environment.flat.ground_height_m` | 有限数 | `flat`の床面を置くローカルZ（m）です。既存City版の離陸地点と高さを合わせる場合は、その地点の`terrain_height_m`を指定します。 |
| `environment.flat.origin.latitude` | -90〜90 | Leaflet表示とDrone位置基準に使う緯度です。物理床の高さには影響しません。 |
| `environment.flat.origin.longitude` | -180〜180 | Leaflet表示とDrone位置基準に使う経度です。 |
| `environment.flat.origin.altitude_offset_m` | 有限数 | Drone simulation locationへ渡す基準標高です。MuJoCoのローカル床Zとは別の値です。 |

`plateau`では`city_world_receipt`が必須です。既定experimentには静岡City Worldへの相対パスと
`altitude_mode: route-clearance`を設定しているため、通常は`mode`を変更するだけで有効になります。
別Cityや別の高度解決方式を一時的に試す場合だけCLIオプションを指定します。

`flat`ではCity World Receiptを参照しません。床面は`ground_height_m`、機体中心の初期Zは
`ground_height_m + --spawn-altitude-m`（既定0.50m）、Formationの最低飛行高度は
`ground_height_m + scenario.altitude_m`として解決されます。既定設定は、直前の静岡City
Worldにおける中央離陸地点の高さへ合わせています。

### `viewer`

| 項目 | 型・制約 | 説明 |
|---|---|---|
| `viewer.network.host` | IPv4アドレス | Viewerを開く端末から到達可能なホストのIPv4アドレスです。`open-viewer`の表示URLとブラウザのWebSocket接続先へ使います。Macだけで見る場合は`127.0.0.1`、同じLANのスマホから見る場合はMacのLAN IPを指定します。HTTPサーバーとWebBridge自体は全インタフェースで待ち受けます。 |
| `viewer.initial_mode` | `free`または`audience` | ブラウザ起動時の視点です。`free`は従来のOrbitカメラ、`audience`は下記の観客視点です。ブラウザ上でいつでも切り替えられます。 |
| `viewer.led_appearance.scale` | 0より大きく4以下 | LEDスプライト全体の表示サイズ倍率です。機体間隔やFormation寸法は変わりません。既定値は`1.45`です。 |
| `viewer.led_appearance.intensity` | 0より大きく4以下 | Show Planで解決された機体別brightnessへ掛ける、画面表示全体の発光強度倍率です。既定値は`1.25`です。 |
| `viewer.led_appearance.spatial_depth_cue` | 真偽値 | `true`では近距離のLEDハローを抑え、立体LEDコアと白い機体を見せます。遠距離では従来どおりLEDを強調します。 |
| `viewer.city_lighting.enabled` | 真偽値 | PLATEAU Viewerの夜間会場照明を有効にします。`flat`では無効になります。 |
| `viewer.city_lighting.brightness` | 0〜3 | 街全体の明るさ倍率です。内部で環境光・方向光・天空光・露出をまとめて調整します。 |
| `viewer.city_lighting.lights.light1`〜`light4` | マッピング | 固定4スロットの会場照明です。省略したスロットには既定値が入ります。 |
| `viewer.city_lighting.lights.lightN.enabled` | 真偽値 | その照明を有効にします。 |
| `viewer.city_lighting.lights.lightN.position_m` | 3要素の数値配列 | 光源を置くローカルENU座標`[East, North, Up]`（m）です。 |
| `viewer.city_lighting.lights.lightN.target_m` | 3要素の数値配列 | 照射先のローカルENU座標`[East, North, Up]`（m）です。光源から照射先への向きが照射方向になります。 |
| `viewer.city_lighting.lights.lightN.brightness` | 0〜5 | その照明の明るさ倍率です。 |
| `viewer.city_lighting.lights.lightN.spread_deg` | 10〜70 | その照明の広がりです。 |
| `viewer.city_lighting.lights.lightN.color` | `#RRGGBB` | 照明色です。暖色の既定値は`#ffd6a0`です。 |
| `viewer.crowd.enabled` | 真偽値 | PLATEAU Viewer上の簡易観客演出を有効にします。`flat`とARページには表示しません。 |
| `viewer.crowd.count` | 1〜2000の整数 | 表示する簡易観客数です。人物は`InstancedMesh`で描画され、物理・PDUには追加されません。 |
| `viewer.crowd.center_m` | 2要素の数値配列 | 観客配置矩形の中心`[East, North]`（m）です。 |
| `viewer.crowd.width_m` | 0より大きく500以下 | 観客配置矩形のEast方向の幅です。 |
| `viewer.crowd.depth_m` | 0より大きく500以下 | 観客配置矩形のNorth方向の奥行きです。Formationの湾曲量とは別設定です。 |
| `viewer.crowd.ground_height_m` | 有限数、省略可能 | 観客の足元を置くローカルZ（m）です。省略時は飛行計画の高度基準を使いますが、道路面とずれる場合は画面を見ながら調整します。静岡の既定値は`5.5`mです。 |
| `viewer.crowd.lighting.enabled` | 真偽値 | 観客エリア四隅の簡易イベント照明を有効にします。 |
| `viewer.crowd.lighting.intensity` | 0〜1000 | 各照明のPointLight強度です。既定値は`140`です。 |
| `viewer.crowd.lighting.height_m` | 0〜50 | 観客の足元から照明までの高さ（m）です。既定値は`4`mです。 |
| `viewer.audience_camera.position_m` | 3要素の数値配列 | 観客カメラの初期位置をローカルENU座標`[East, North, Up]`（m）で指定します。 |
| `viewer.audience_camera.yaw_deg` | 数値 | 水平向きです。0度はEast、正方向はNorth側です。 |
| `viewer.audience_camera.pitch_deg` | -85〜85 | 仰角です。0度は水平、正方向は上です。 |
| `viewer.audience_camera.fov_deg` | 25〜90 | 垂直画角です。小さいほど望遠、大きいほど広角になります。 |

観客視点では、矢印キーで前後左右、`U`/`D`で上下へ移動します。`Shift`を
押しながら移動すると高速になります。左ドラッグでyaw、右ドラッグでpitch、
マウスホイールでFOVを調整します。調整内容はブラウザ内だけに保持され、YAMLは
自動更新されません。観客視点のパネルには現在のENU位置、yaw、pitch、FOVが表示されます。
3D画面右上の方位HUDには、観客視点・自由視点のどちらでも現在の視線方向を
コンパス方位（0°=北、90°=東）で表示します。「風を操作」の流れる方向（to）と同じ方位基準なので、
機体が画面上のどちらへ流れるかを確認できます。カメラ設定のyawはENU基準（0°=東、
90°=北）のため、数値を比較するときは右上HUDを使用してください。
`YAML設定をコピー`で`audience_camera`ブロックをコピーし、`viewer`の下へ反映してから
`configure`を再実行してください。

`viewer.led_appearance`はThree.js上の見え方だけを調整します。Show PlanのLED
`brightness`（0〜1）は機体・フレーム別の演出値であり、こちらの設定では変更しません。

`viewer.city_lighting`を有効にすると、左パネルへ折りたたみ式の`会場照明を調整`が表示されます。
街の明るさと、選択中の照明の有効状態・明るさ・広がり・色は即座にViewerへ反映されます。
照明1〜4をセレクトで切り替え、`光源位置`または`照射先`を選びます。調整パネルを開いている間は
3D画面に選択中の光源、照射先、照射線が表示されます。位置は地図クリック、東西南北のコンパス、
高さボタンで移動できます。`YAML設定をコピー`で4灯すべての現在値をコピーし、
City experiment YAMLの`viewer`直下へ貼り付けてから`configure`を再実行してください。
ブラウザ上の変更だけでは次回起動時の設定は変わりません。

`viewer.crowd`は会場の無人感を抑えるための見栄え優先の演出です。観客はFormation方向へ
向いた明るい簡易人型として決定論的に配置され、一部はスマートフォンの光を持ちます。
夜間照明で黒いシルエットにならないよう、人物色は照明非依存です。terrainの細かな起伏や
歩道境界への厳密な追従は行わないため、配置範囲から多少はみ出す場合があります。
照明を有効にすると、配置範囲の四隅に暖色と淡い青の光源を交互に置き、足元にも薄い光だまりを
表示します。会場の寂しさを抑えるための演出であり、MuJoCoの物理世界には追加されません。

スマホ表示ではMacとスマホを同じLANへ接続し、`viewer.network.host`へMacのLAN IPを
設定して`configure`を再実行します。`open-viewer`が表示するURLをスマホで開いてください。
IPアドレスが変わった場合もYAMLを更新して再度`configure`します。このHTTP接続は現行
ViewerのLAN疎通確認用です。カメラARは専用のHTTPS/WSS Gatewayを使用します。

`configure`は同じURLを格納した次のファイルも生成します。Macで`viewer-qr.svg`を開き、
スマホのカメラで読み取ると長いURLを入力せずにViewerを開けます。QR生成は同梱の純Python
encoderを使用するため、pip packageや外部Webサービスを必要としません。

```text
work/recipes/drone-fleet-single-host/viewer-access/viewer-url.txt
work/recipes/drone-fleet-single-host/viewer-access/viewer-qr.svg
```

### `ar`

| 項目 | 型・制約 | 説明 |
|---|---|---|
| `ar.enabled` | 真偽値 | カメラ重畳ARページとHTTPS/WSS Gatewayを有効にします。 |
| `ar.venue.latitude` | -90〜90 | Showの会場基準緯度です。 |
| `ar.venue.longitude` | -180〜180 | Showの会場基準経度です。 |
| `ar.venue.heading_deg` | 有限数 | 地理ENUからShow ENUへの会場方位です。360度で正規化されます。 |
| `ar.preview.location_source` | `device`または`override` | AR開始時の初期観客位置です。`device`はGPSを一度だけ取得します。 |
| `ar.preview.override.latitude` | -90〜90 | 遠隔テスト用の仮想観客緯度です。 |
| `ar.preview.override.longitude` | -180〜180 | 遠隔テスト用の仮想観客経度です。 |
| `ar.preview.eye_height_m` | 0より大きく10以下 | 平面床から観客カメラまでの高さです。 |
| `ar.preview.movement_speed_m_s` | 0より大きく100以下 | 折りたたみ式の仮想移動ボタンを押している間の移動速度です。 |
| `ar.preview.device_orientation` | `off`または`optional` | `optional`はAR開始時に端末姿勢の利用許可を求め、yaw/pitchへ反映します。 |

ARの初期位置は端末GPSまたは`override`から一度だけ計算し、必要な場合だけ画面右下から
仮想位置を調整します。
編隊中心への方向と距離はAR画面上のガイドへ表示されます。利用手順、証明書、操作方法は[カメラARプレビュー](ar-preview.md)を
参照してください。

### `scenario`

| 項目 | 型・制約 | 説明 |
|---|---|---|
| `scenario.show_file` | experimentからの相対パス | 機体数非依存のShow Fileです。SVG一覧、実行順、移動・待機時間、LEDを定義します。詳細は[Show File v1](show-file-v1.md)を参照してください。 |
| `scenario.formation.scale_m` | 0より大きい数値 | 全Formationの公称最大寸法（m）です。顔の大きさを直接調整する項目です。詳細は「Formationの大きさ」を参照してください。 |
| `scenario.formation.depth_m` | 0以上`scale_m`以下 | Formation中央を観客側へ湾曲させる最大奥行き（m）です。`0`は平面です。 |
| `scenario.formation.audience_tilt_deg` | -85〜85の数値 | Formation平面を水平面から起こす角度（度）です。0度は上空から見やすい水平、絶対値が90度に近いほど地上の観客へ正対し、符号で傾斜方向が反転します。現在は反対方向を確認できるよう`-60`度に設定しています。`configure --formation-tilt-deg`で一時上書きできます。 |
| `scenario.altitude_m` | 0.5以上の数値 | `flat`では床からのFormation最低高度（AGL）です。`plateau`ではCity飛行計画が要求する最低クリアランスで、最終高度はCity colliderと`--altitude-mode`等から解決されます。 |
| `scenario.max_speed_m_s` | 0より大きい数値 | 機体へ許可する最大移動速度（m/s）です。実際の指令速度は各機体の移動距離をShow Fileの`transition_sec`で割って求めます。configureは必要最大速度がこの値を超える計画をエラーにし、runtimeにも同じ上限を安全策として渡します。値を大きくしても計画時刻より早く到着する設定にはなりません。 |
| `scenario.timeout_sec` | 1以上の数値 | Fleet命令の完了待ちに使うtimeout（秒）です。遅い移動を設定する場合は必要に応じて増やします。 |
| `scenario.land` | 真偽値 | `true`ならShow終了後に着陸します。現在のCityデモは`false`で、明示的に`stop`するまで最後のFormationを保持します。 |

`audience_tilt_deg`は人が理解しやすい「水平面から起こす角度」です。Show Planの
`tilt_deg`は鉛直軸からの角度なので、configure時に符号を保った補角へ変換します。
例えばYAMLの60度はShow Planの30度、YAMLの-60度はShow Planの-30度になります。

汎用Business Packが内部で要求する`type`、`word`、`letter_width_m`、
`letter_height_m`、`letter_gap_m`、`duration_sec`、`hold_sec`、`speed_m_s`はShow operatorが互換値を補います。これらは
`virtual-drone-show-city.yaml`の公開設定ではなく、指定するとエラーになります。互換用
FormationもCityの経路クリアランス計算に使われるため、その外形寸法は`scale_m`に
比例して自動生成されます。

### `results`

| 項目 | 型・制約 | 説明 |
|---|---|---|
| `results.enabled` | 真偽値 | Business Packの結果収集を有効にします。現在の観賞用Cityデモでは`false`です。 |
| `results.directory` | workspace内の相対パス | 結果を有効にした場合の出力先です。絶対パスと`..`は指定できません。 |

## 生成物

`configure`はYAMLを解決し、Fleet分割、flight plan、Show Plan、Show IR、Launcherを
生成します。次の生成物を直接編集せず、experiment、Show File、SVGの入力を変更して
再度`configure`してください。

- `resolved-experiment.yaml`
- `config/mujoco-city-fleet.json`（`plateau`）または`config/mujoco-flat-fleet.json`（`flat`）
- `config/scenario/show-ir/show-plan.json`
- `config/scenario/show-ir/show-ir.json`
- `runtime/launcher.json`
