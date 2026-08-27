# Show File v1

Show Fileは、機体数に依存しないドローンショーのユーザインタフェースです。使用する
SVG Formation、実行順、移動時間、待機時間、LEDを1つのJSONに記述します。
Formation JSON、Resolved Show Plan、Show IRを直接編集させないためのファサードであり、
ショー制作におけるユーザ入力の正本です。

既定の例は`shows/kids-space-adventure.show.json`です。以前の3顔デモは
`shows/three-face.show.json`として残しています。

```json
{
  "schema_version": "1.0",
  "show_id": "three-face-show",
  "title": "Three Face Show",
  "assignment": { "strategy": "index" },
  "formations": [
    {
      "formation_id": "round-ear-face",
      "title": "Round-ear face",
      "svg": "../assets/formations/round-ear-face.svg"
    }
  ],
  "timeline": [
    {
      "step_id": "face-1",
      "formation_id": "round-ear-face",
      "transition_sec": 6.0,
      "hold_sec": 10.0,
      "led": {
        "effect": "steady",
        "rgb": [255, 64, 96],
        "brightness": 1.0
      }
    }
  ]
}
```

`formations[].svg`はShow Fileからの相対パスです。`timeline`では同じ
Formationを複数回参照できます。現在のLED effectは`steady`のみです。

## LEDの色分け

単色で表示する場合は、上の例のように`led`へRGB、brightness、effectを直接指定します。
この従来の簡潔な形式は、全pointへ適用する`default`として扱われます。

絵柄の一部を色分けする場合は、SVG要素へFormation固有の`data-led-role`を付け、
Show Fileの`roles`でそのroleのLED状態を指定します。

```xml
<path data-led-role="body" d="..."/>
<circle data-led-role="window" cx="80" cy="72" r="17"/>
<polyline data-led-role="flame" points="..."/>
```

```json
"led": {
  "default": {
    "effect": "steady",
    "rgb": [232, 244, 255],
    "brightness": 1.0
  },
  "roles": {
    "window": {
      "effect": "steady",
      "rgb": [64, 176, 255],
      "brightness": 1.0
    },
    "flame": {
      "effect": "steady",
      "rgb": [255, 72, 24],
      "brightness": 1.0
    }
  }
}
```

`led_role`は`eyes`や`flame`など、その絵柄の中で意味を持つFormationローカルな名前です。
共通語彙へ固定する必要はありません。同じroleを持つpointにはrole指定を適用し、指定の
ないroleおよび`data-led-role`のないpointには`default`を適用します。Show Fileで指定した
roleが対象Formationに存在しない場合、スペルミスやSVGとの不整合として`configure`を
エラーにします。

既定の子供向けショーでは、この形式によりネコの目、ロケットの窓と炎、UFOのライト、
AIロボットのアンテナなどを色分けしています。

## 機体数との関係

Show FileとSVGには機体数を書きません。`configure`はexperimentの
`scale.drone_count`を読み、各SVGをその点数へ再サンプリングして、機体数入りの
Formation JSON、Show Plan、Show IRを生成します。

```text
Show File + SVG             機体数非依存（編集する正本）
            + scale.drone_count
                    ↓ configure
Formation / Show Plan / IR  機体数依存（自動生成物）
```

したがって、同じShow Fileを128機、180機などで再利用できます。ただし、実行可能な
機体数は使用中の箱庭コア/Drone PROプロファイルの上限に従います。また、点数が少ないほど
SVGの細部は粗くなります。

## 切り替え手順

1. 既存ファイルをコピーし、`formations`と`timeline`を編集する。
2. 色分けする場合はSVGへ`data-led-role`を付け、timelineの`led.roles`へ色を定義する。
3. experimentの`scenario.show_file`を新しいファイルへ変更する。
4. Launcherを正規終了し、`configure`を再実行する。

```bash
python3 tools/show_file.py shows/my-show.show.json
python3 tools/recipe/virtual_drone_show.py stop
python3 tools/recipe/virtual_drone_show.py configure

# environment.mode: plateauの場合はenvironment.plateauの設定を使用
python3 tools/recipe/virtual_drone_show.py configure
```

JSON Schemaの正本は`schemas/show-file-v1.schema.json`です。

## 従来の`scenario/show.json`との違い

Drone PROの従来Runnerが読む`scenario/show.json`は、汎用Business Packとの互換性を保つ
ための内部形式です。本書のShow Fileとは別の概念です。新しいショーではShow Fileを編集し、
`configure`が生成したShow IRをShow Experience Runnerへ渡します。
