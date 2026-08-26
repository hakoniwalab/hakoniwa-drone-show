# Hakoniwa Formation JSON v0.1

## 目的

Formation JSONは、SVG等から生成した再利用可能な形状点群です。点の形状上の意味と
LED roleを保持しますが、特定のショー、LED状態、機体、時刻、City Worldには依存しません。

```text
SVG / future authoring input
          ↓ sample・normalize
     Formation JSON
          ↓ Show Plan・assignment・timing
        Show IR
```

JSON Schemaの正本は
[`schemas/formation-v0.1.schema.json`](../schemas/formation-v0.1.schema.json)です。

## Show IRとの責務境界

Formation JSONに含めるもの:

- 安定した`formation_id`
- 指定個数へsample済みのpoints
- point IDとgroup ID
- Formationローカルの正規化位置
- 各pointの`led_role`
- 任意の入力種別、入力hash、URI

Formation JSONに含めないもの:

- Drone IDと機体割当
- ショー開始からの時刻
- 移動時間、hold時間、step順序
- City Worldの緯度・経度・heading
- 前後Formation間のtrajectory
- SVG pathやベンダー固有field
- LEDのRGB、brightness、点灯effect

Show Planは複数のFormationを参照し、順序、transform、移動時間、hold時間、LED演出を
指定します。compilerはそれらを割当・時刻付きのShow IRへ完全展開します。Show IRは
実行時にFormation JSONを参照しません。

## 座標

`position`は`[right, up, depth]`の順を持つ`FORMATION_LOCAL`座標です。単位は
`normalized`で、City上のメートルではありません。SVG変換ではSVGの下向きYを反転して
`up`とし、初期実装では`depth=0`とします。

SVG変換器はsample後のbounding box中心を原点とし、最大extentが1になるように正規化
します。Show Plan側のscaleと姿勢が、この座標をShow IRのローカルENUメートルへ変換
します。

## pointとgroup

- `point_id`はFormation内で一意かつ決定的に生成する
- `group_id`は輪郭、目、内部パーツなどの意味的なまとまりを表す
- `led_role`はShow Planから色や点灯効果を指定するための意味的な役割を表す
- `points`の順序も同じ入力から決定的に生成する
- LEDのRGB、brightness、点灯effectはShow Planだけが所有する

point IDとgroup IDは機体割当時の連続性やLED roleの解決に利用できますが、Drone IDでは
ありません。

## source

`source`は任意のprovenance情報です。`sha256`は入力byte列のhashであり、生成された
Formation JSON自身のhashではありません。`uri`は追跡用で、実行時依存にはしません。
ライセンス情報は将来のShow Receiptまたは配布manifestで管理します。

## サンプルと検証

```bash
python3 tools/formation.py validate examples/formations/diamond-4.json
```

validatorは構造、座標、LED範囲に加えてpoint IDの一意性を検証します。

現行3フェーズデモの抽象モチーフは、SVG原画と128点のFormationとして次に格納します。

- `assets/formations/round-ear-face.svg` → `examples/formations/round-ear-face-128.json`
- `assets/formations/cat-ear-face.svg` → `examples/formations/cat-ear-face-128.json`
- `assets/formations/long-ear-face.svg` → `examples/formations/long-ear-face-128.json`

これらは特定キャラクターの公式データではなく、円・多角形・楕円から構成した手続き的な
デモ図形です。SVGが原画の正本であり、JSONは次のコマンドで決定的に再生成できます。

```bash
python3 tools/generate_demo_formations.py
python3 tools/formation.py validate examples/formations/round-ear-face-128.json
python3 tools/formation.py validate examples/formations/cat-ear-face-128.json
python3 tools/formation.py validate examples/formations/long-ear-face-128.json
```

各部品は`head`、`left-eye`等のgroupを保ち、`outline`、`eyes`、`mouth`、`accent`
というLED roleを持ちます。色・点滅・表示時間はFormationでは固定せず、Show Planで
指定します。

## SVGからの変換

任意のSVGは次のように変換します。

```bash
python3 tools/svg_to_formation.py assets/formations/round-ear-face.svg \
  --formation-id round-ear-face-128 \
  --points 128 \
  --title "Round-ear face (128 points)" \
  --source-uri assets/formations/round-ear-face.svg \
  --output examples/formations/round-ear-face-128.json
```

初版converterは外部Pythonパッケージに依存せず、各要素の輪郭を等弧長sampleします。

- 対応要素: `path`、`circle`、`ellipse`、`rect`、`line`、`polyline`、`polygon`、`g`
- 対応path command: `M`、`L`、`H`、`V`、`C`、`S`、`Q`、`T`、`Z`と各相対形式
- 対応transform: `matrix`、`translate`、`scale`、`rotate`、`skewX`、`skewY`
- SVGの`id`または`data-group-id`をFormationの`group_id`へ引き継ぐ
- `data-led-role`を`led_role`へ引き継ぎ、未指定時は`default`とする
- 各輪郭の`data-weight`を点数配分比に使い、未指定時は輪郭長で自動配分する
- SVGの下向きYをFormationの上向き`up`へ反転し、sample後に正規化する
- 非表示要素と`defs`は点群化しない
- 入力SVGのSHA-256と追跡用URIをFormationの`source`へ記録する

同じ`group_id`を複数要素に付けることは可能で、point IDの連番はgroup全体で一意に
なります。`data-weight`はSVG標準属性ではなく、本ツール用のauthoring hintです。

SVG arc path command `A`、`use`参照、stroke幅、塗り領域の内部sample、CSSによる複雑な
表示判定は初版の対象外です。arcは`circle`／`ellipse`またはBezier pathへ変換してから
入力します。未対応commandは黙って無視せず、明確な変換エラーにします。
