# ドローンショー制作ツールチェーン利用手順

この手順では、SVG原画からFormationを生成し、Show Planと初期Fleet位置を組み合わせて
完全展開済みのShow IRを作成・検証します。箱庭、MuJoCo、Drone PROは不要です。

```text
SVG
 ↓ svg_to_formation.py
Formation JSON ─┐
                ├─ show_compiler.py ─> Show IR ─> validator
Show Plan ──────┤
Initial State ──┘
```

## 前提

- Python 3.10以降
- `hakoniwa-drone-show`のリポジトリrootでコマンドを実行
- 外部Pythonパッケージは不要

## 1. SVG原画を用意する

サンプルは[`assets/formations/`](../assets/formations/)にあります。SVGの各輪郭へ、
必要に応じて次の属性を設定します。

```xml
<ellipse id="left-eye"
         data-led-role="eyes"
         data-weight="0.07"
         cx="-0.27" cy="0.05" rx="0.065" ry="0.105"/>
```

- `id`: Formationの`group_id`
- `data-led-role`: Show PlanからLED状態を指定するrole
- `data-weight`: この輪郭へ配分する機体数の相対weight。省略時は輪郭長

対応SVG要素と制約は[Formation仕様](formation-v0.1.md#svgからの変換)を参照してください。

## 2. SVGをFormationへ変換する

1ファイルだけ変換する場合:

```bash
python3 tools/svg_to_formation.py \
  assets/formations/cat-ear-face.svg \
  --formation-id cat-ear-face-128 \
  --points 128 \
  --title "Cat-ear face (128 points)" \
  --source-uri assets/formations/cat-ear-face.svg \
  --output examples/formations/cat-ear-face-128.json
```

リポジトリ付属の3図形をまとめて再生成する場合:

```bash
python3 tools/generate_demo_formations.py
```

200機または256機へ変更して試す場合:

```bash
python3 tools/generate_demo_formations.py \
  --point-count 256 \
  --output /tmp/hakoniwa-formations-256
```

生成後に検証します。

```bash
python3 tools/formation.py validate \
  examples/formations/cat-ear-face-128.json
```

## 3. Show Planを編集する

サンプルは
[`examples/show-plans/three-face-demo.json`](../examples/show-plans/three-face-demo.json)
です。主に次を編集します。

- `fleet`: 機体数、Drone ID、割当方式
- `formations`: Formationへの相対pathとSHA-256
- `defaults`: 既定の移動時間、待機時間、配置、LED
- `timeline`: Formationの順序とstep別の上書き

```json
{
  "step_id": "cat-ear",
  "formation_id": "cat-ear-face-128",
  "transition_sec": 8.0,
  "hold_sec": 10.0
}
```

Formationを再生成するとファイルhashが変わります。次のコマンド等でSHA-256を取得し、
Planの`formations[].sha256`を更新します。

macOSでは`shasum -a 256`、Ubuntuでは`sha256sum`を使えます。

```bash
# macOS
shasum -a 256 examples/formations/cat-ear-face-128.json

# Ubuntu
sha256sum examples/formations/cat-ear-face-128.json
```

Planと参照Formationをまとめて検証します。

```bash
python3 tools/show_plan.py validate \
  examples/show-plans/three-face-demo.json
```

## 4. 初期Fleet位置を用意する

Show IRの時刻0には全Droneの初期位置が必要です。オフライン確認ではcentered gridを生成
できます。

```bash
mkdir -p work/toolchain

python3 tools/initial_fleet_state.py generate-grid \
  --drone-count 128 \
  --prefix Drone- \
  --start 1 \
  --spacing-m 1.5 \
  --altitude-m 0.0 \
  --output work/toolchain/initial-fleet-state.json
```

```bash
python3 tools/initial_fleet_state.py validate \
  work/toolchain/initial-fleet-state.json
```

このgridはオフライン制作確認用です。実行用Show IRを作る場合は、Recipeが生成した実際の
Drone ID・初期ENU位置を同じInitial Fleet State形式で出力して使用します。PlanとStateの
Drone ID集合だけでなく、配列順も一致する必要があります。
形式の正本は
[`schemas/initial-fleet-state-v0.1.schema.json`](../schemas/initial-fleet-state-v0.1.schema.json)
です。

## 5. Show IRをcompileする

```bash
python3 tools/show_compiler.py \
  --plan examples/show-plans/three-face-demo.json \
  --initial-state work/toolchain/initial-fleet-state.json \
  --output work/toolchain/three-face-show-ir.json
```

このサンプルでは次の結果になります。

```text
drones=128
frames=7
frame times=0, 8, 14, 22, 28, 36, 42 sec
duration=42 sec
```

生成したShow IRを検証します。

```bash
python3 tools/show_ir.py validate \
  work/toolchain/three-face-show-ir.json
```

Show IRは自動生成物です。位置、時刻、Drone ID、LEDが完全展開されているため、通常は
手で編集しません。内容を変更する場合はSVGまたはShow Planを修正して再compileします。

## 6. 現在の実行範囲

本手順で、SVGからShow IRまでのオフライン生成と検証は完結します。現在のShow Runnerは
まだ従来の`show.json`を入力としているため、生成したShow IRをMuJoCoショーで直接実行する
接続は次段階です。

接続時もICRAおよびDrone PROの既存Runnerは変更せず、本リポジトリのShow Experience
RunnerへShow IR adapterを追加します。接続完了までは従来Recipeの実行手順を利用します。

## 7. 回帰テスト

```bash
python3 -m unittest discover -s tools -p 'test_*.py'
```

テストはSVG変換の決定性、Formation参照hash、機体数、時刻展開、index／nearest-greedy
割当、transform、hold、LED role解決、Show IR意味制約を確認します。
