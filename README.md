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

## Task 0: 現行Cityショーの実行

Task 0では、Business Packで動作していたCityドローンショーを、機能を追加せず
本リポジトリの入口から再現します。次のリポジトリを同じ親ディレクトリへ配置します。

```text
business-pack/
  hakoniwa-business-pack/
  hakoniwa-drone-pro/
  hakoniwa-drone-show/
  hakoniwa-threejs-drone/
```

City WorldはBusiness PackのCity World Workerで生成済みとし、その
`city-world-receipt.json`を指定します。

```bash
cd hakoniwa-drone-show

python3 tools/recipe/virtual_drone_show.py configure \
  --mujoco-city-world \
  ../hakoniwa-business-pack/work/remote-operation/city-world-worker/jobs/<JOB_ID>/build/world/city-world-receipt.json \
  --altitude-mode route-clearance

python3 tools/recipe/virtual_drone_show.py doctor
python3 tools/recipe/virtual_drone_show.py start
python3 tools/recipe/virtual_drone_show.py status
python3 tools/recipe/virtual_drone_show.py open-viewer
python3 tools/recipe/virtual_drone_show.py stop
```

`route-clearance`は離陸地点から各Formationまでの計画経路上にある最高コライダーを
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
`stop`はLauncher control endpointへ`terminate`を送り、管理アセットをcleanupします。
シミュレーション状態だけを変更する`hako-cmd stop`の代用ではありません。

```bash
python3 tools/recipe/virtual_drone_show.py status
python3 tools/recipe/virtual_drone_show.py stop
# TERMINATEDを確認してからconfigureを再実行する
```

`configure`はBusiness Packの汎用`drone-fleet-single-host` workspaceへ成果物を
生成します。以後のコマンドは、そのとき保存されたexperiment、Drone PRO、City World
およびViewer設定を再利用するため、通常は同じ引数を繰り返す必要がありません。
Show用PDU、Bridge経路、Web UIも同workspaceの生成物へ追加されます。Drone Show利用後に
Business Packの汎用Fleet Recipeへ戻る場合は、汎用Recipe側で`configure`を再実行して
workspaceを再生成してから起動してください。

既定配置を変更する場合は、`HAKONIWA_BUSINESS_PACK_ROOT`環境変数と
`--drone-root`、`--viewer-root`、`--experiment`を使用します。

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

## Show toolchain v0.1

Formation JSONはSVG等から生成する再利用可能な正規化点群、Show IRは機体割当・時刻・
位置・LED状態が確定済みの実行・検証フォーマットです。Show Planは両者の間でFormation
の順序、移動・待機時間、配置、LED演出を記述します。

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

箱庭、Drone PRO、Viewerを起動せず、標準Pythonだけで検証できます。

```bash
python3 tools/formation.py validate examples/formations/diamond-4.json
python3 tools/generate_demo_formations.py
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
