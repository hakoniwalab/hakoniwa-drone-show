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

# plateau modeだけCity World Receiptを指定する
python3 tools/recipe/virtual_drone_show.py configure \
  --mujoco-city-world \
  ../hakoniwa-business-pack/work/remote-operation/city-world-worker/jobs/<JOB_ID>/build/world/city-world-receipt.json \
  --altitude-mode route-clearance
```

## Formationの大きさ

`scenario.formation.scale_m`は、SVGから作られた正規化Formationを実空間へ展開した
ときの公称最大寸法です。元Formationの幅・高さ・奥行きの最大spanが`scale_m`メートルに
なるよう、全軸へ同じ倍率を適用します。縦横比は変わりません。

```yaml
scenario:
  formation:
    scale_m: 15.33125
```

この値を小さくすると顔全体が小さくなり、大きくすると拡大します。現在の
`15.33125 m`は、移行前の約`61.325 m`に対して厳密に1/4の大きさです。
`--formation-scale 20`を`configure`へ渡すと、その実行に限りYAMLの値を`20 m`で
上書きできます。

`scale_m`はFormationの向き（yaw/tilt）を適用する前の公称寸法です。向きを変えた後の
ENU各軸のaxis-aligned bounding boxは、回転によってこの値より小さく見える場合が
あります。

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

### `runtime`

| 項目 | 型・制約 | 説明 |
|---|---|---|
| `runtime.mode` | 現在は`native` | ホスト上で動かすruntime方式です。 |
| `runtime.visualization` | 真偽値 | VSP、WebBridge、HTTP ViewerをLauncherへ含めます。ブラウザ開始型のShowでは`true`が必須です。 |
| `runtime.show_runner_real_time_sync` | 真偽値 | Show Runnerの進行をwall-clock時間へ同期します。観賞用Showでは通常`true`にします。 |

### `environment`

| 項目 | 型・制約 | 説明 |
|---|---|---|
| `environment.mode` | `plateau`または`flat` | `plateau`はCity World Receiptの都市mesh・terrain・colliderをMuJoCoとViewerへ組み込みます。`flat`は都市データを一切使わず、Droneと平面床だけの軽量MuJoCo Worldを生成します。 |
| `environment.flat.ground_height_m` | 有限数 | `flat`の床面を置くローカルZ（m）です。既存City版の離陸地点と高さを合わせる場合は、その地点の`terrain_height_m`を指定します。 |
| `environment.flat.origin.latitude` | -90〜90 | Leaflet表示とDrone位置基準に使う緯度です。物理床の高さには影響しません。 |
| `environment.flat.origin.longitude` | -180〜180 | Leaflet表示とDrone位置基準に使う経度です。 |
| `environment.flat.origin.altitude_offset_m` | 有限数 | Drone simulation locationへ渡す基準標高です。MuJoCoのローカル床Zとは別の値です。 |

`flat`では`--mujoco-city-world`は不要です。床面は`ground_height_m`、機体中心の初期Zは
`ground_height_m + --spawn-altitude-m`（既定0.20m）、Formationの最低飛行高度は
`ground_height_m + scenario.altitude_m`として解決されます。既定設定は、直前の静岡City
Worldにおける中央離陸地点の高さへ合わせています。

### `viewer`

| 項目 | 型・制約 | 説明 |
|---|---|---|
| `viewer.network.host` | IPv4アドレス | Viewerを開く端末から到達可能なホストのIPv4アドレスです。`open-viewer`の表示URLとブラウザのWebSocket接続先へ使います。Macだけで見る場合は`127.0.0.1`、同じLANのスマホから見る場合はMacのLAN IPを指定します。HTTPサーバーとWebBridge自体は全インタフェースで待ち受けます。 |
| `viewer.initial_mode` | `free`または`audience` | ブラウザ起動時の視点です。`free`は従来のOrbitカメラ、`audience`は下記の観客視点です。ブラウザ上でいつでも切り替えられます。 |
| `viewer.led_appearance.scale` | 0より大きく4以下 | LEDスプライト全体の表示サイズ倍率です。機体間隔やFormation寸法は変わりません。既定値は`1.45`です。 |
| `viewer.led_appearance.intensity` | 0より大きく4以下 | Show Planで解決された機体別brightnessへ掛ける、画面表示全体の発光強度倍率です。既定値は`1.25`です。 |
| `viewer.audience_camera.position_m` | 3要素の数値配列 | 観客カメラの初期位置をローカルENU座標`[East, North, Up]`（m）で指定します。 |
| `viewer.audience_camera.yaw_deg` | 数値 | 水平向きです。0度はEast、正方向はNorth側です。 |
| `viewer.audience_camera.pitch_deg` | -85〜85 | 仰角です。0度は水平、正方向は上です。 |
| `viewer.audience_camera.fov_deg` | 25〜90 | 垂直画角です。小さいほど望遠、大きいほど広角になります。 |

観客視点では、矢印キーで前後左右、`U`/`D`で上下へ移動します。`Shift`を
押しながら移動すると高速になります。左ドラッグでyaw、右ドラッグでpitch、
マウスホイールでFOVを調整します。調整内容はブラウザ内だけに保持され、YAMLは
自動更新されません。観客視点のパネルには現在のENU位置、yaw、pitch、FOVが表示されます。
`YAML設定をコピー`で`audience_camera`ブロックをコピーし、`viewer`の下へ反映してから
`configure`を再実行してください。

`viewer.led_appearance`はThree.js上の見え方だけを調整します。Show PlanのLED
`brightness`（0〜1）は機体・フレーム別の演出値であり、こちらの設定では変更しません。

スマホ表示ではMacとスマホを同じLANへ接続し、`viewer.network.host`へMacのLAN IPを
設定して`configure`を再実行します。`open-viewer`が表示するURLをスマホで開いてください。
IPアドレスが変わった場合もYAMLを更新して再度`configure`します。このHTTP接続は現行
ViewerのLAN疎通確認用です。カメラとWebXRを使うAR版では、後続TaskでHTTPS/WSSを追加します。

`configure`は同じURLを格納した次のファイルも生成します。Macで`viewer-qr.svg`を開き、
スマホのカメラで読み取ると長いURLを入力せずにViewerを開けます。QR生成は同梱の純Python
encoderを使用するため、pip packageや外部Webサービスを必要としません。

```text
work/recipes/drone-fleet-single-host/viewer-access/viewer-url.txt
work/recipes/drone-fleet-single-host/viewer-access/viewer-qr.svg
```

### `scenario`

| 項目 | 型・制約 | 説明 |
|---|---|---|
| `scenario.show_file` | experimentからの相対パス | 機体数非依存のShow Fileです。SVG一覧、実行順、移動・待機時間、LEDを定義します。詳細は[Show File v1](show-file-v1.md)を参照してください。 |
| `scenario.formation.scale_m` | 0より大きい数値 | 全Formationの公称最大寸法（m）です。顔の大きさを直接調整する項目です。詳細は「Formationの大きさ」を参照してください。 |
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
