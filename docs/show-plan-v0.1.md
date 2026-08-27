# Hakoniwa Show Plan JSON v0.1

## 目的

Show Planは、再利用可能なFormationをどの順序、位置、時間、LED状態で見せるかを記述する
authoring形式です。Drone IDごとの座標と絶対時刻を列挙するShow IRとは責務が異なります。

```text
SVG ──変換──> Formation JSON
                    ＋
              Show Plan
                    ＋
        初期Fleet位置（compiler入力）
                    ↓ assignment・resolve
                 Show IR
```

JSON Schemaの正本は
[`schemas/show-plan-v0.1.schema.json`](../schemas/show-plan-v0.1.schema.json)です。

## ルート要素

| field | 内容 |
|---|---|
| `schema_version` | v0.1では文字列`0.1` |
| `show_id` | Show Planを識別する安定したID |
| `title` | 任意の表示名 |
| `time_unit` | `second` |
| `placement` | 任意のCity World配置。Show IRと同じ形式 |
| `fleet` | 機体数、Drone ID生成規則、割当方式 |
| `formations` | Formation ID、相対path、ファイルSHA-256 |
| `defaults` | 時間、transform、LEDの既定値 |
| `timeline` | Formationを表示する順序とstep別上書き |

Show Plan内のpathはPlanファイルからの相対pathです。ネットワーク取得や絶対pathは使いません。
validatorとcompilerはFormationファイルのSHA-256、内部`formation_id`、point数を照合します。

## Fleetと割当

`drone_id_pattern`は`prefix + zero-paddingした連番`でShow IRのDrone IDを生成します。
サンプルでは`Drone-1`から`Drone-128`になります。

v0.1の`assignment.strategy`は次の2種類です。

- `index`: Drone ID順の第N機をFormationの第N pointへ割り当てる
- `nearest-greedy`: 初期位置または直前stepの位置から、Drone ID順に最寄りの未割当pointを
  選ぶ。距離が同じ場合はFormationのpoint順を使う

Show IRの時刻0に必要な初期Fleet位置は、Show Planではなくcompiler引数として与えます。
これにより同じ演出をpacked gridなど異なる離陸配置から生成できます。最初のstepの
`transition_sec`は、その初期位置から最初のFormationへ移動する時間です。

## Formation transform

Formationの`[right, up, depth]`をShow IRのローカルENUメートルへ変換します。

- `scale_m`: Formationの正規化座標1.0に対応するメートル数
- `translation_m`: `[east, north, up]`のFormation原点
- `yaw_deg`: ENU Up軸周りの反時計回り回転。0度ではrightがEast、depthがNorth
- `tilt_deg`: Formation right軸周りの傾斜。正値では上端がNorth側へ傾く
- `depth_m`（任意）: 左右端を保ち、中央を観客側へ湾曲させる最大奥行き。既定値0

角度をラジアンへ変換し、`R=(cos(yaw), sin(yaw), 0)`、`D=(-sin(yaw), cos(yaw), 0)`、
`U=(0,0,1)`とします。tilt後の軸は`U'=cos(tilt)U+sin(tilt)D`、
`D'=-sin(tilt)U+cos(tilt)D`です。Formation point `(right,up,depth)`は次でENUへ
変換します。

```text
translation_m + scale_m * (right*R + up*U' + depth*D')
```

`depth_m > 0`の場合、Formationの左右範囲を`[-1, 1]`へ正規化した値を`r`として、
各pointへ`-depth_m * max(0, 1-r²) * D'`を加えます。これにより正面投影を維持した
円筒状の奥行きを作ります。

stepに`transform`がなければ`defaults.transform`をそのまま使います。v0.1のstep別
transformは部分差分ではなく必須4 fieldすべてを指定します。`depth_m`は省略できます。

## timing

各stepは次の順で進みます。

1. 直前の状態から対象Formationへ`transition_sec`秒で線形移動
2. 到達した位置で`hold_sec`秒待機
3. 次のstepへ進む

stepに値がなければ`defaults`を使います。v0.1の`transition_sec`は0より大きく、
`hold_sec`は0以上でなければなりません。サンプルは各stepが8秒＋6秒で、全3 stepの
合計は42秒です。

## LED

`defaults.led.default`は全pointへ適用する既定状態です。`roles`はFormation pointの
`led_role`へ適用します。step側の指定を含む優先順位は次のとおりです。

1. stepのrole指定
2. stepのdefault指定
3. defaultsのrole指定
4. defaultsのdefault指定

同じ配列内で同一`led_role`を複数回指定できません。Formationに存在しないstep別roleは
validatorがエラーにします。

stepのLED状態は対象Formationへの到着frameで有効になります。移動中は直前frameのLEDを
保持し、到着後は次のstepで変更されるまで同じ状態を保持します。

v0.1で実行可能なeffectは`steady`だけです。`effect`を明示するtagged構造にしてあるため、
将来のSchema versionで`blink`や`fade`固有パラメータを追加できます。点滅やfadeを曖昧な
意味で先に固定せず、シミュレーション時刻とShow IRへの展開規則を定義するTask 3で追加
します。

## 既存show.jsonとの対応

現在のDrone PRO向け`show.json`はruntime入力として維持し、新しいShow Plan Schemaを
直接適用しません。compiler／adapter段階では次の対応で移行します。

| 既存show.json | Show Plan v0.1 |
|---|---|
| `formation_files[].id` | `formations[].formation_id` |
| `formation_files[].path` | `formations[].path` |
| `timeline[].formation` | `timeline[].formation_id` |
| `timeline[].duration_sec` | `timeline[].transition_sec` |
| `timeline[].hold_sec` | `timeline[].hold_sec` |
| Recipeで事前適用したscale・回転・傾斜 | `defaults/step.transform` |

既存Runnerを先に変更せず、Show PlanからShow IRを生成して同等性を確認した後に接続します。
そのためICRAおよび従来の`show.json`経路へ、このSchema追加だけで挙動変更は発生しません。

## サンプルと検証

[`examples/show-plans/three-face-demo.json`](../examples/show-plans/three-face-demo.json)は、
3つの128点Formationを現在のショーと同じ時間順で表示します。

SVGからShow IRまでの通し手順は[ツールチェーン利用手順](toolchain-guide.md)を参照して
ください。

```bash
python3 tools/show_plan.py validate examples/show-plans/three-face-demo.json
```

通常のvalidationは参照Formationも読み込み、hash、ID、point数、LED roleを検証します。
Plan JSONだけを検証したい場合は`--skip-files`を指定します。

```bash
python3 tools/show_plan.py validate --skip-files \
  examples/show-plans/three-face-demo.json
```
