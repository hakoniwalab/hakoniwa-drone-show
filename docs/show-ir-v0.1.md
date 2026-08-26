# Hakoniwa Show IR v0.1

## 目的

Hakoniwa Show IRは、制作ツールやベンダー固有形式から独立して、箱庭上でドローン
ショーを実行・表示・検証するためのresolved中間表現です。制作時の意図ではなく、
機体割当と時刻が確定した実行結果を表します。

```text
SVG / authoring show.json / vendor data
                 ↓ adapter・sample・assignment・resolve
          Hakoniwa Show IR
                 ↓
       Show Runner / Viewer / validator
```

JSON Schemaの正本は[`schemas/show-ir-v0.1.schema.json`](../schemas/show-ir-v0.1.schema.json)
です。

## Authoring入力との境界

SVGは線、輪郭、group、色などを保持するauthoring入力です。既存の`show.json`は
Formationの順序、移動時間、hold時間などを指定するauthoring planです。どちらにも、
最終的なDrone ID割当や絶対時刻が未確定の情報を含められます。

SVGからsample・正規化した再利用可能な点群の正本は
[`Hakoniwa Formation JSON v0.1`](formation-v0.1.md)です。Show PlanはFormation JSONを
参照し、compilerがその内容をShow IRのtimelineへ展開します。

Show IRにはSVG path、Formation名、割当アルゴリズム、生成理由を保存しません。
resolverが全Drone ID、時刻、位置、LED状態を確定した後の成果物だけを格納します。

## ルート要素

| field | 内容 |
|---|---|
| `schema_version` | v0.1では文字列`0.1` |
| `show_id` | 生成物を識別する安定したID |
| `title` | 任意の表示名 |
| `time_unit` | `second`。ショー開始を0秒とする |
| `coordinate_system` | `ENU`、位置単位`meter` |
| `placement` | 任意のCity World配置情報 |
| `interpolation` | position=`linear`、LED=`hold` |
| `drone_ids` | 割当済みDrone IDの完全な集合 |
| `timeline` | `time_sec`昇順のresolved frame |

## 座標とplacement

`position_m`は`[east, north, up]`の順で、placement原点からのローカルENUメートルです。
`placement`を省略した場合、利用側が与えたローカルENU原点へ配置します。

`placement`を指定する場合、緯度・経度をENU原点とし、`altitude_offset_m`を全位置の
Upへ加算します。`heading_deg`は真北を0度として上空から見た時計回りの回転です。
Hakoniwa/ROS座標への変換は実行Adapterが一度だけ行い、Show IR自体には混在させません。

## timelineと補間

- 最初のframeは`time_sec=0`とする
- frame時刻は厳密な昇順とする
- 全frameは`drone_ids`に列挙した全機体を一度ずつ含む
- 各frameの`states`は決定的な出力のため`drone_ids`と同じ順序にする
- frame間のpositionはENU各軸を線形補間する
- LEDの`rgb`と`brightness`は次のframeまで保持する
- 同じ位置を後続frameへ記述することでhold時間を表現する

RGBは0..255の整数3要素、brightnessは0..1です。v0.1のShow RunnerはLED値を無視して
現在の表示を維持できますが、resolverは将来のViewer実装が同じIRを利用できるよう
全frameへ明示的なLED状態を出力します。

## Drone ID

Drone IDは1..64文字の文字列で、英数字から始まり、英数字、`.`、`_`、`-`を利用します。
`drone_ids`の順序は決定的な出力や機体割当に利用できますが、実行時の同一性は文字列で
判定します。

## v0.1の非目標

衝突回避、最小機体間隔、geofence、速度・加速度・jerk制約、実機ID、RTK/GNSS、
航空法・安全管理情報、SVG等の制作元データ、ベンダー固有fieldは含めません。
trajectoryから計算可能な検証値は、Show IRを書き換えずvalidatorやreportで扱います。

## 最小サンプルと検証

[`examples/show-ir/minimal.json`](../examples/show-ir/minimal.json)は2機の離陸と3秒holdを
表します。

```bash
python3 tools/show_ir.py validate examples/show-ir/minimal.json
```

validatorはJSON Schemaで表現する構造制約に加え、先頭時刻、時刻順、frame内のDrone ID
重複、および全frameの機体集合一致を検証します。
