# Cityドローンショー設定

`recipes/experiments/virtual-drone-show-city.yaml`は、City World上で実行する
Virtual Drone Showの既定experimentです。この文書は設定項目の正本です。

設定を変更した場合は、生成済みShow IRやLauncherへ自動反映されません。Launcherを
正規終了してから`configure`を再実行してください。

```bash
python3 tools/recipe/virtual_drone_show.py stop
python3 tools/recipe/virtual_drone_show.py status

# statusがTERMINATEDであることを確認する
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

### `scenario`

| 項目 | 型・制約 | 説明 |
|---|---|---|
| `scenario.formation.scale_m` | 0より大きい数値 | 全Formationの公称最大寸法（m）です。顔の大きさを直接調整する項目です。詳細は「Formationの大きさ」を参照してください。 |
| `scenario.altitude_m` | 0.5以上の数値 | City飛行計画が要求する最低クリアランス（m）の既定値です。最終高度はCity colliderと`configure`時の`--altitude-mode`、`--above-city-clearance-m`等から解決され、生成markerとShow IRへ記録されます。 |
| `scenario.duration_sec` | 0より大きい数値 | 各顔Formationへの移動に割り当てる時間（秒）です。Show Planの各stepの`transition_sec`になります。 |
| `scenario.hold_sec` | 0以上の数値 | 各顔Formationを到達後に維持する時間（秒）です。Show Planの各stepの`hold_sec`になります。 |
| `scenario.max_speed_m_s` | 0より大きい数値 | 機体へ許可する最大移動速度（m/s）です。実際の指令速度は各機体の移動距離を`duration_sec`で割って求めます。configureは必要最大速度がこの値を超える計画をエラーにし、runtimeにも同じ上限を安全策として渡します。値を大きくしても`duration_sec`より早く到着する設定にはなりません。 |
| `scenario.timeout_sec` | 1以上の数値 | Fleet命令の完了待ちに使うtimeout（秒）です。遅い移動を設定する場合は必要に応じて増やします。 |
| `scenario.land` | 真偽値 | `true`ならShow終了後に着陸します。現在のCityデモは`false`で、明示的に`stop`するまで最後のFormationを保持します。 |

汎用Business Packが内部で要求する`type`、`word`、`letter_width_m`、
`letter_height_m`、`letter_gap_m`、`speed_m_s`はShow operatorが互換値を補います。これらは
`virtual-drone-show-city.yaml`の公開設定ではなく、指定するとエラーになります。互換用
FormationもCityの経路クリアランス計算に使われるため、その外形寸法は`scale_m`に
比例して自動生成されます。

### `results`

| 項目 | 型・制約 | 説明 |
|---|---|---|
| `results.enabled` | 真偽値 | Business Packの結果収集を有効にします。現在の観賞用Cityデモでは`false`です。 |
| `results.directory` | workspace内の相対パス | 結果を有効にした場合の出力先です。絶対パスと`..`は指定できません。 |

## 生成物

`configure`はYAMLを解決し、Fleet分割、City flight plan、Show Plan、Show IR、Launcherを
生成します。次の生成物を直接編集せず、YAMLまたはFormation/Show Planの入力を変更して
再度`configure`してください。

- `resolved-experiment.yaml`
- `config/mujoco-city-fleet.json`
- `config/scenario/show-ir/show-plan.json`
- `config/scenario/show-ir/show-ir.json`
- `runtime/launcher.json`
