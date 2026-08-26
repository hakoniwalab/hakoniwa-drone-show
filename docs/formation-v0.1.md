# Hakoniwa Formation JSON v0.1

## 目的

Formation JSONは、SVG等から生成した再利用可能な形状点群です。点の形状上の意味と
既定LED属性を保持しますが、特定のショー、機体、時刻、City Worldには依存しません。

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
- 各pointの`led_role`と任意の既定RGB・brightness
- 任意の入力種別、入力hash、URI

Formation JSONに含めないもの:

- Drone IDと機体割当
- ショー開始からの時刻
- 移動時間、hold時間、step順序
- City Worldの緯度・経度・heading
- 前後Formation間のtrajectory
- SVG pathやベンダー固有field

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
- `default_led`は任意で、指定する場合のRGBは0..255、brightnessは0..1
- Show Planに指定がなく`default_led`もない場合はcompilerが白、brightness=1を適用する

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
