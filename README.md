# hakoniwa-drone-show

Hakoniwa向けバーチャルドローンショーの制作、計画、検証および実行機能を管理する
非公開プロジェクトです。

本リポジトリは次の汎用機能を所有します。

- ショー計画とresolved show planの仕様
- Formation制作と指定機体数への点群化
- 機体割当、Transition planning、事前検証
- LED演出計画
- Show Experience Runner、開始待機、Show Status通知
- 計画プレビューと実行summary
- PRO環境を前提とするバーチャルドローンショー専用Recipeとexperiment
- iPhone/Android共通のカメラ重畳ARプレビュー
- 平面Formationを実3D座標へ湾曲させる奥行き演出と距離適応LED
- PLATEAU会場の無人感を抑える軽量な観客演出

## 実装配置の原則

ドローンショーの利用体験、制作、計画、検証、進行管理に関して新しく追加する機能は、
原則として本リポジトリへ実装します。Business Packの特定Recipeで最初に必要になった
機能でも、ショー固有かつ再利用可能であれば本リポジトリを正本とします。

例外は、次のOwner固有部分だけです。

- 汎用Recipe基盤、City World生成、配布・納品統合: `hakoniwa-business-pack`
- Fleet制御とDrone runtime: `hakoniwa-drone-pro`
- ブラウザUIと地図表示: `hakoniwa-map-viewer`
- DroneのThree.js描画: `hakoniwa-threejs-drone`
- City、地形、風などの環境生成: `hakoniwa-envsim`

Ownerリポジトリへ変更が必要な場合も、ショー仕様と接続契約は本リポジトリで定義し、
Business Packへ代替実装を複製しません。

一般利用可能なFleet性能検証RecipeはBusiness Packに残します。PRO環境が必須となる
CityドローンショーのRecipe、専用experiment、Formation素材および統合テストは、
本リポジトリを正本とします。

City World、Recipe、Launcher、Viewer接続および納品パッケージへの統合は
[`hakoniwa-business-pack`](https://github.com/hakoniwalab/hakoniwa-business-pack)が担当します。

## Task 0: ドローンショーRuntimeの実行

Task 0では、Business Packで動作していたCityドローンショーを、機能を追加せず
本リポジトリの入口から再現します。次のリポジトリを同じ親ディレクトリへ配置します。

```text
business-pack/
  hakoniwa-business-pack/
  hakoniwa-drone-pro/
  hakoniwa-drone-show/
  hakoniwa-threejs-drone/
```

既定experimentは`environment.mode: flat`で、都市データを使わない平面MuJoCo Worldを
生成します。

```bash
cd hakoniwa-drone-show

python3 tools/recipe/virtual_drone_show.py configure
python3 tools/recipe/virtual_drone_show.py doctor
python3 tools/recipe/virtual_drone_show.py start
python3 tools/recipe/virtual_drone_show.py status
python3 tools/recipe/virtual_drone_show.py open-viewer
python3 tools/recipe/virtual_drone_show.py stop
```

## カメラARプレビュー

ARページはWebXRへ依存せず、端末カメラ映像へ透明なThree.js描画を重ねます。iPhone
SafariとAndroid Chromeで共通の基盤を使い、Android WebXR対応は将来追加できます。

初期観客位置は起動時に端末の緯度経度を一度だけ取得して会場基準ENUへ変換します。
以後GPSへ追従せず、必要な場合だけ右下の小さな移動ボタンから仮想位置を調整します。
編隊が視野外なら画面端の矢印で位置を案内します。視野内では中央マーカーを出さず、
左上の距離ボタンで距離表示を切り替えます。左下には初期位置からの前後左右移動、
地面からの高さ、最寄り機までの距離を表示します。端末姿勢によるyaw/pitch連動はYAMLで
有効・無効を選べます。

iPhoneでカメラと現在地を利用するため、ARページは生成したローカルCAを信頼した上で
HTTPS/WSS Gatewayから開きます。初回だけ次の手順が必要です。

1. `configure`後、`viewer-access/hakoniwa-ar-ca.crt`をAirDrop等でiPhoneへ渡してインストールする。
2. iPhoneの「設定 → 一般 → 情報 → 証明書信頼設定」で`Hakoniwa Drone Show Local CA`を信頼する。
3. `doctor`、`start`後に`viewer-access/ar-viewer-qr.svg`を読み取る。
4. カメラARを開始し、カメラと現在地を許可する。

MacからURLを確認する場合は次を使用します。

```bash
python3 tools/recipe/virtual_drone_show.py open-ar
```

通常ViewerのHTTP `:8000`とWebSocket `:8765`は変更しません。AR専用Gatewayは
HTTPS `:8443`の同一オリジン上でARページと`/pdu`のWSSを提供します。互換・診断用の
WSS `:8766`も維持します。詳細は[ARプレビュー手順](docs/ar-preview.md)を
参照してください。PLATEAU City版からAR版へ段階的に対応した設計・検証の順序は
[PLATEAU City版からAR版への対応手順](docs/ar-porting-procedure.md)に残しています。

PLATEAU City Worldを使う場合はYAMLを`environment.mode: plateau`へ変更します。使用する
Receiptと高度解決方式は`environment.plateau`へ固定できるため、通常はCLI指定不要です。

```bash
python3 tools/recipe/virtual_drone_show.py configure
```

別のCity Worldまたは高度解決方式を一時的に使う場合だけ、`--mujoco-city-world`または
`--altitude-mode`でYAMLを上書きします。

既定の`route-clearance`は離陸地点から各Formationまでの計画経路上にある最高コライダーを
基準に飛行高度を決めます。ショーを近く見せる通常のデモではこちらを使用します。
生成City全体で最も高い建物より上を常に飛ばしたい場合だけ、より保守的な
`--altitude-mode city-max-clearance`を指定します。

機体数とMuJoCoプロセス数の既定値はexperimentの`scale.drone_count`と
`scale.process_count`で管理します。各プロセスの担当機数はこの2値から均等に自動分割
されるため、`drones_per_process`は指定しません。例えば128機・6プロセスは
`21, 21, 21, 21, 22, 22`機に分割されます。一度だけ上書きする場合はconfigureへ
次のオプションを追加します。

```bash
  --drone-count 128 \
  --process-count 6
```

configureはFleet分割、MuJoCoモデル、Show IR、Launcher設定を再生成します。稼働中の
workspaceへconfigureを重ねず、先にRecipe所有Launcherを正規終了してください。
operatorも既存session fileを確認し、状態が`TERMINATED`でなければconfigureを拒否します。
`stop`はLauncher control endpointへ`terminate`を送り、管理アセットをcleanupします。
シミュレーション状態だけを変更する`hako-cmd stop`の代用ではありません。

```bash
python3 tools/recipe/virtual_drone_show.py status
python3 tools/recipe/virtual_drone_show.py stop
# TERMINATEDを確認してからconfigureを再実行する
```

`configure`はBusiness Packの汎用`drone-fleet-single-host` workspaceへ成果物を
生成します。以後のコマンドは、そのとき保存されたexperiment、Drone PRO、環境World
およびViewer設定を再利用するため、通常は同じ引数を繰り返す必要がありません。
Show用PDU、Bridge経路、Web UIも同workspaceの生成物へ追加されます。Drone Show利用後に
Business Packの汎用Fleet Recipeへ戻る場合は、汎用Recipe側で`configure`を再実行して
workspaceを再生成してから起動してください。

既定配置を変更する場合は、`HAKONIWA_BUSINESS_PACK_ROOT`環境変数と
`--drone-root`、`--viewer-root`、`--experiment`を使用します。

既定experimentのFormationサイズ、速度、待機時間、プロセス数など、YAML全項目の意味と
変更後の再生成手順は
[`docs/virtual-drone-show-city-config.md`](docs/virtual-drone-show-city-config.md)を
参照してください。

移行baseline、主要生成物hash、確認結果は
[`docs/task0-baseline.md`](docs/task0-baseline.md)に記録しています。
Fleet制御は既存の`hakoniwa-drone-pro`を利用し、そのShow Runnerを本リポジトリへ
複製しません。

## Task 1: ブラウザから開始する

Task 1対応Recipeでは、`start`しても自動的に離陸しません。`open-viewer`で専用画面を
開くとWebSocketへ自動接続し、Show Runnerと全機の初期位置が揃った時点で
`ドローンショー開始`ボタンが有効になります。

専用画面とShow Experience Runnerは、既存WebBridgeの同じTCP port 8765を使います。
開始・状態通知用に別のWebSocket serverやportを追加しません。通信frame、PDU channel、
重複STARTの扱いは[`docs/show-control-protocol.md`](docs/show-control-protocol.md)を
参照してください。

既存の汎用Map Viewer画面とICRA実行経路は変更せず、専用画面はRecipe生成物の
`/drone-show/index.html`として追加されます。

観客視点では現在のENU位置、yaw、pitch、FOVをサイドパネルへ表示します。調整後に
3D画面右上には、風操作コンパスと同じ0°=北・90°=東の基準でカメラの視線方位を表示します。
風操作の矢印は風が実際に流れる方向（to）を示します。
風パネルはManualとLiveを切り替えられます。Liveはconfigureで解決した会場座標の
Open-Meteo気象モデル値を既定5分間隔で取得し、気象風向（from）から流れる方向（to）へ
変換します。`最新値を取得`で即時更新でき、取得に使用したAPI URLも画面から確認できます。
Liveでも機体ごとの風速標準偏差は変更可能です。gustは参考表示だけに使用します。

再現実験ではCity experimentの`global_wind.scenario.enabled`を`true`にし、
`global_wind.scenario.file`へWind Scenario v1 JSONを指定してから`configure`します。
Scenarioは離陸完了を0秒とする箱庭時刻で進み、ブラウザのManual／Live入力より優先されます。
実行中は現在イベントの方向、平均風速、標準偏差が風コンパスへ自動表示されます。
サンプルは[`examples/wind-scenarios/osaka-gust-east.json`](examples/wind-scenarios/osaka-gust-east.json)、
設定項目と戻し方は
[`docs/virtual-drone-show-city-config.md`](docs/virtual-drone-show-city-config.md)を参照してください。

Show Runnerは全機takeoff完了直後の`DroneStatus.collided_counts`をbaselineとして即時保存し、
Wind Scenarioの最終イベントから10秒後の値をfinalとして取得します。baselineは
`work/recipes/drone-fleet-single-host/validation/execution-summary.baseline.json`、差分集計は
`work/recipes/drone-fleet-single-host/validation/execution-summary.json`に
`collision_evaluation`として保存されます。この値はMuJoCoの新規contact geom pair数であり、
事故件数や建物だけの接触回数を意味しません。

Live WeatherデモはOpen-Meteo Free APIを利用します。Free APIの利用条件とrate limitは
Open-Meteoの現行Termsに従い、Weather dataはOpen-Meteoへの帰属表示を伴います。この機能は
気象モデル由来の値をシミュレーション表示へ用いるもので、実飛行・航空気象・安全判断には
使用できません。商用利用時はOpen-Meteoの利用条件とAPI planを別途確認してください。
`YAML設定をコピー`を押すと、City experimentへ貼り付ける`audience_camera`設定を
クリップボードへコピーできます。

専用画面はruntime用Show IRをHTTPで読み、Show Statusの`show_frame_index`に同期して
機体ごとのRGBとbrightnessを表示します。現在のCityデモは3つのFormationを赤、緑、黄で
順番に表示します。LED指定を行わない既存Viewerでは、従来の水色breathing表示がそのまま
fallbackとして使われます。

## ショーを作るために用意するファイル

ユーザが用意・編集する入力は、次の3種類です。生成されたFormation JSON、Resolved
Show Plan、Show IRを直接編集する必要はありません。

1. **SVGファイル** — 各Formationの原画です。機体数は指定しません。
2. **Show File（`*.show.json`）** — 使用するSVG、Formationの実行順、移動時間、待機時間、LEDを定義します。
3. **City experiment YAML** — 機体数、プロセス数、Show Fileへの参照、Formationの大きさ・傾斜、高度、最大速度、Viewer設定を定義します。

既定の入力は次のファイルです。

- SVG: [`assets/formations/`](assets/formations/)
- Show File: [`shows/kids-space-adventure.show.json`](shows/kids-space-adventure.show.json)
- City experiment: [`recipes/experiments/virtual-drone-show-city.yaml`](recipes/experiments/virtual-drone-show-city.yaml)

`configure`は`scale.drone_count`を使い、入力から実行用成果物までを自動生成します。

```text
SVG + Show File + City experiment YAML
                    ↓ configure
機体数分のFormation JSON
                    ↓
Resolved Show Plan
                    ↓
Show IR
                    ↓
Fleet設定・Launcher・Viewer設定
```

SVGとShow Fileは機体数非依存です。Formation JSON、Resolved Show Plan、Show IRは
機体数依存の自動生成物です。機体数を変更した場合は`configure`を再実行してください。
各SVGは新しい機体数へ再サンプリングされ、後続成果物も作り直されます。実行可能な
最大機体数は、使用する箱庭コアおよびDrone PROプロファイルの上限に従います。

Show Fileの形式と新しいショーへの切り替え手順は
[`docs/show-file-v1.md`](docs/show-file-v1.md)を参照してください。

既定のShow Fileは、180機向けの子供向け演目「ネコと宇宙の大冒険」です。ネコ、
T-Rex、ロケット、UFOと宇宙人、AIロボットを順番に表示します。以前の3顔デモも
[`shows/three-face.show.json`](shows/three-face.show.json)として残してあり、
`scenario.show_file`を変更すれば切り替えられます。

SVG要素の`data-led-role`とShow Fileの`led.roles`を組み合わせると、絵柄ごとに目、窓、
炎などを色分けできます。role未指定部分には`led.default`が適用されます。詳細は
[`docs/show-file-v1.md`](docs/show-file-v1.md#ledの色分け)を参照してください。

## Show toolchain v0.1

Show toolchainは、次の4つの概念を扱います。

| 概念 | 編集者 | 機体数依存 | 責務 |
|---|---|---|---|
| **Show File（`*.show.json`）** | ユーザ | なし | SVG参照、Formationの実行順、移動・待機時間、LEDをまとめるユーザインタフェースです。 |
| **Formation JSON** | ツール | あり | SVG等から指定機体数で生成する、再利用可能な正規化点群です。 |
| **Resolved Show Plan** | ツール | あり | Formation参照、機体数、配置、時間、LEDを解決した中間計画です。 |
| **Show IR** | ツール | あり | 機体割当・時刻・位置・LED状態が確定済みの実行・検証フォーマットです。これだけ読めばショーを実行できます。 |

Show Fileは、Formation、Show Plan、Show IRを直接編集させないためのファサードであり、
ショー制作におけるユーザ入力の正本です。

なお、Drone PROの従来Runnerが読む互換用`scenario/show.json`はShow Fileではありません。
本RecipeはShow IR経路を使用し、互換用`scenario/show.json`は汎用Business Packの内部生成物
として扱います。ユーザが新しいショーを作る場合は、`shows/*.show.json`相当のShow Fileを
編集してください。

- [`docs/formation-v0.1.md`](docs/formation-v0.1.md)
- [`schemas/formation-v0.1.schema.json`](schemas/formation-v0.1.schema.json)
- [`assets/formations/`](assets/formations/)
- [`examples/formations/diamond-4.json`](examples/formations/diamond-4.json)
- [`examples/formations/round-ear-face-128.json`](examples/formations/round-ear-face-128.json)
- [`examples/formations/cat-ear-face-128.json`](examples/formations/cat-ear-face-128.json)
- [`examples/formations/long-ear-face-128.json`](examples/formations/long-ear-face-128.json)

- [`docs/show-plan-v0.1.md`](docs/show-plan-v0.1.md)
- [`schemas/show-plan-v0.1.schema.json`](schemas/show-plan-v0.1.schema.json)
- [`examples/show-plans/three-face-demo.json`](examples/show-plans/three-face-demo.json)
- [`schemas/initial-fleet-state-v0.1.schema.json`](schemas/initial-fleet-state-v0.1.schema.json)

- [`docs/show-ir-v0.1.md`](docs/show-ir-v0.1.md)
- [`schemas/show-ir-v0.1.schema.json`](schemas/show-ir-v0.1.schema.json)
- [`examples/show-ir/minimal.json`](examples/show-ir/minimal.json)
- [`docs/toolchain-guide.md`](docs/toolchain-guide.md)

City Showで使用するFormation、実行順、時間、LEDは、機体数非依存のShow File
[`shows/three-face.show.json`](shows/three-face.show.json)で切り替えられます。形式と
変更手順は[`docs/show-file-v1.md`](docs/show-file-v1.md)を参照してください。

箱庭、Drone PRO、Viewerを起動せず、標準Pythonだけで検証できます。

```bash
python3 tools/formation.py validate examples/formations/diamond-4.json
python3 tools/generate_demo_formations.py
python3 tools/show_file.py shows/three-face.show.json
python3 tools/svg_to_formation.py assets/formations/round-ear-face.svg \
  --formation-id round-ear-face-128 --points 128 \
  --output /tmp/round-ear-face-128.json
python3 tools/show_plan.py validate examples/show-plans/three-face-demo.json
python3 tools/initial_fleet_state.py generate-grid \
  --drone-count 128 --output /tmp/initial-fleet-state.json
python3 tools/show_compiler.py \
  --plan examples/show-plans/three-face-demo.json \
  --initial-state /tmp/initial-fleet-state.json \
  --output /tmp/three-face-show-ir.json
python3 tools/show_ir.py validate examples/show-ir/minimal.json
python3 -m unittest tools.test_formation
python3 -m unittest tools.test_show_ir
```

`configure`は実際のFleet初期位置、Show-owned SVG、Show Planからruntime用Show IRを
`config/scenario/show-ir/show-ir.json`へ自動生成します。Launcherは本リポジトリの
Show Experience Runnerへ`--show-ir`を渡します。Drone PROの既存RunnerとICRA経路は
変更せず、`--show-ir`がない場合は従来の`show.json`経路を利用します。

現在の設計・実装タスクは[`task.md`](task.md)を参照してください。
