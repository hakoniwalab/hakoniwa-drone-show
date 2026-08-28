# PLATEAU AWARD Decision Evidence Pack

## 目的

PLATEAU City上のドローンショーについて、新しいシミュレーション機能を増やすのではなく、
シミュレーション結果を受けて計画を改善できたことを、同一条件の比較、数値、画像、Receiptで
説明可能にする。

作品の位置付けは、安全認証または実機運航可否の判定ではなく、次とする。

> PLATEAUを物理的にリハーサル可能な都市空間へ自動変換し、任意都市で多数機ドローンショーの
> 演出、見え方、都市との離隔、風外乱への応答を事前比較できる制作支援環境。

キャッチコピーは次とする。

> **都市を舞台にする前に、都市でリハーサルする。**

## 成功条件

一つの会場と一つの演目について、次の3ケースを比較する。

1. 計画A・無風
2. 計画A・突風あり
3. 改善した計画B・計画Aと同一の突風あり

同一の都市、演目、機体数、観客カメラおよび風入力を使用し、計画変更前後の違いを定量的に
説明できれば完了とする。建物接触を意図的に発生させることは成功条件にしない。

最低限、次を一つのRehearsal Reportへ残す。

- 計画Aから計画Bへ変更した理由と変更値
- RMS位置誤差
- 95パーセンタイル位置誤差
- Formation成立率
- 同一観客カメラによる計画A／Bの画像
- Show IR、風シナリオ、seed、Git commitを含む実行条件
- 本結果の適用範囲と免責

接触情報を正しく観測・分類できる場合は、接触機体数、接触時間、最初の接触時刻も追加する。

## 比較条件

| 条件 | A：無風 | A：突風 | B：突風 |
| --- | --- | --- | --- |
| 会場 | 同一 | 同一 | 同一 |
| 元SVG／Show File | 同一 | 同一 | 同一 |
| 機体数 | 同一 | 同一 | 同一 |
| 観客カメラ | 同一 | 同一 | 同一 |
| 風シナリオ | 無風 | gust scenario | 同じgust scenario |
| seed | 固定 | 固定 | 同じseed |

計画Aは無風で妥当な候補案とし、比較用に不自然な衝突条件を作らない。A・突風の結果を確認して
から計画Bを決める。計画Bの変更は最大2項目とし、候補は次とする。

- ショー中心を建物から離す
- Formation高度を調整する
- Formationサイズを縮小する
- Formation遷移時間を変更する

遷移時間の延長は必ず改善するとは限らない。現在のRunnerは移動距離と`transition_sec`から
指令速度を決めるため、測定結果を確認せず変更内容を固定しない。

## ランタイム構成

```text
Wind Scenario JSON
       │
       │ Hakoniwa virtual time + fixed seed
       ▼
Global Wind Asset
       │
       ├─ Drone-0 Disturbance
       ├─ Drone-1 Disturbance
       └─ Drone-N Disturbance

Show IR ───────────────┐
                       ▼
Visual State PDU ── Rehearsal Observer
                       │
                       ├─ summary.json
                       ├─ timeseries.csv
                       └─ execution receipt
                                  │
                                  ▼
                        Rehearsal Report HTML
```

## 風シナリオ

Manual／Liveとは別に、AWARD比較用の再現可能なScenarioモードを追加する。ブラウザのwall clockで
再生せず、Global Wind Assetが箱庭仮想時刻を基準にイベントを適用する。

概念例:

```json
{
  "schema_version": 1,
  "scenario_id": "gust-east-to-southeast",
  "seed": 12345,
  "events": [
    {"time_sec": 0, "enabled": true, "speed_m_s": 0.0, "direction_to_deg": 90},
    {"time_sec": 15, "enabled": true, "speed_m_s": 4.0, "direction_to_deg": 90},
    {"time_sec": 30, "enabled": true, "speed_m_s": 8.0, "direction_to_deg": 120},
    {"time_sec": 36, "enabled": true, "speed_m_s": 4.0, "direction_to_deg": 90}
  ],
  "vehicle_variation": {
    "type": "fixed_gain",
    "speed_stddev_m_s": 0.32
  }
}
```

機体ごとの風は、既存Global Wind Assetと同様に、同一方向の共通風へ固定seedから生成した速度差を
与える。毎周期独立乱数は使用しない。

固定seedで保証するのは、同一の風イベント列と各機体へ配布される同一の風ベクトル列である。
複数MuJoCoプロセスを含む実行結果のbit単位一致は要求せず、評価指標が定めた許容差内で再現する
ことを確認する。

ScenarioモードとManual／Liveが同時に風を更新しないよう、Scenario実行中の入力優先順位または
排他規則を明示する。比較実行ではScenarioを正本とする。

## 評価メトリクス

評価周期は5〜10Hz程度とし、200機分の全周期・全状態を巨大CSVへ保存せずオンライン集計する。

各機体の位置誤差を次で定義する。

```text
e_i(t) = norm(actual_position_i(t) - planned_position_i(t))
```

必須指標:

- RMS位置誤差
- 95パーセンタイル位置誤差
- 最大位置誤差
- Formation成立率

Formation成立率は、各評価時刻において計画位置から指定許容距離以内に存在する機体の割合を求め、
対象区間で平均した値とする。許容距離は実行条件へ明記する。

接触情報を正しく取得できる場合の追加指標:

- 一度でも対象へ接触した機体数
- 全機体の接触継続時間合計
- 最初の接触時刻

MuJoCoの接触を毎ステップ単純加算した「接触回数」は使用しない。建物、地面、他機体を分類できない
場合は「建物接触」と表記しない。外部から接触状態を取得できない場合は、今日の比較指標から外す。

建物との最小離隔は、既存機能から低コストで取得できる場合だけ追加する。全Droneと全Colliderの
距離計算を新規実装することは、このタスクの必須範囲に含めない。

## 座標系の検証

メトリクス実装前に、一機の既知位置を使って次の経路が一致することを確認する。

```text
Show IR ENU
    ↓
Runner command coordinates
    ↓
Drone / MuJoCo runtime
    ↓
Visual State PDU
    ↓
Observer ENU
```

Show IRの計画位置とVisual Stateの実位置を、座標系と符号を確認せず直接比較しない。既知位置の
変換テストを自動テストとして残す。

## 出力形式

概念上、比較ケースは次の構造で管理する。

```text
rehearsal-case/
├── venue.yaml
├── plan-a.yaml
├── plan-b.yaml
├── wind-gust.json
├── results/
│   ├── a-calm/
│   │   ├── summary.json
│   │   └── timeseries.csv
│   ├── a-gust/
│   │   ├── summary.json
│   │   └── timeseries.csv
│   └── b-gust/
│       ├── summary.json
│       └── timeseries.csv
├── report/
│   ├── rehearsal-report.html
│   ├── tracking-error.png
│   ├── formation-rate.png
│   ├── audience-plan-a.png
│   └── audience-plan-b.png
└── README.md
```

実際の配置は既存Recipe、runtime、Receipt構成へ合わせる。初回実装では3ケースの完全自動運転や
画像の自動撮影を必須にせず、同一条件を確認できるmanifestと再実行手順を優先する。

### `summary.json`

```json
{
  "rms_position_error_m": 0.0,
  "p95_position_error_m": 0.0,
  "max_position_error_m": 0.0,
  "formation_success_rate": 0.0,
  "contacted_vehicle_count": null,
  "total_contact_time_sec": null,
  "first_contact_time_sec": null
}
```

取得できない指標を0として記録しない。`null`または項目省略で、未測定とゼロを区別する。

### `timeseries.csv`

```text
time_sec,rms_error_m,p95_error_m,formation_success_rate,contact_vehicle_count
```

必要であれば、代表機体または最大誤差機体について計画位置と実位置を別途保存し、軌道比較図へ
使用する。

## Rehearsal Report

静的HTMLを正本とし、大規模なWebダッシュボードは作らない。

### Venue

- 都市名
- PLATEAUデータ年度
- LOD
- メッシュコード
- 元データ識別情報またはURL
- City World Receiptおよび変換アセットのhash

### Show

- Show File、元SVGおよびShow IRの識別情報とhash
- 機体数
- ショー時間
- 計画A／Bの変更内容

### Environment

- 風シナリオ名とhash
- seed
- 風イベント
- Open-Meteo値を初期条件として利用した場合の座標、データ時刻、取得時刻
- Open-Meteo値が現地観測ではなく気象モデル由来である旨

### Results

- A・無風／A・突風／B・突風の比較表
- 位置誤差の時系列グラフ
- Formation成立率の時系列グラフ
- 同一観客カメラによるA／B画像
- 取得できた場合は接触情報

### Decision

結果を受けて、計画Aの何を、なぜ、どの値へ変更したかを記載する。結論は測定後に作成し、先に
期待結果を固定しない。

### Scope

次を明記する。

> 本結果は、指定した都市モデル、機体モデル、制御モデルおよび外乱シナリオにおける物理
> リハーサル結果です。実際の運航可否、安全性または法令適合性を保証するものではありません。

### Provenance

- Git commit SHA
- 実行日時
- 箱庭仮想時刻
- Show IR hash
- 風シナリオhash
- seed
- 評価周期
- Formation成立許容距離

## Task AWARD-0: 実現可能性スパイク

- [ ] Show IRの計画位置を任意の仮想時刻で補間できることを確認する
- [ ] Visual Stateの実位置を評価用ENUへ正しく変換できることを確認する
- [ ] 一機の既知位置で計画位置と実位置の座標系を検証する
- [ ] 5〜10Hzで200機を評価できることを確認する
- [ ] Collision PDUまたは既存出力から接触状態を観測できるか確認する
- [ ] 接触相手を建物、地面、他機体へ分類できるか確認する
- [ ] 接触指標を今回採用するか判断する

### 静的確認メモ（2026-08-28）

- 実位置は既存`DroneVisualStatePublisher`の`DroneVisualStateArray`から取得できる。PDUは
  `sequence_id`、chunk情報、`start_index`、`valid_count`と、各機体の`x/y/z`を持つ。
- Python側にも`DroneVisualStateArray`の生成済みdecoderがあり、Web Viewerだけに依存せず
  ObserverからSHM上の集約PDUを読む構成にできる見込みである。
- Runnerは各motionのtarget、duration、phase開始箱庭時刻を保持している。外部ObserverがShow IRの
  絶対時刻だけから計画位置を推測すると、takeoff、非同期goto完了、holdの実際の開始時刻とずれる
  可能性がある。Runnerから離陸完了を0とする`show_time_usec`を約250 ms間隔で通知するようにしたが、
  計画位置の厳密な補間には各phaseの実開始時刻も正本として扱う必要がある。
- City fleetの生成Receiptでは`city_to_drone=enabled`、`drone_to_drone=disabled`になっている。
  Drone PROのMuJoCo実装は、各機体geomと相手geomの新規接触ペアを`collided_counts`へ累積し、
  各機体の`status` PDU（channel 18、`hako_msgs/DroneStatus`）へ毎周期書き戻している。MuJoCo resetで
  カウンタは0へ戻る。既存サンプルと同様、全機のtakeoff完了後かつShow IR時系列開始直前
  （`show_time_usec=0`）の値をbaseline、最後のFormation／hold完了後かつland開始前の値をfinalとして、
  機体ごとの`final - baseline`を集計すれば飛行演出区間だけの接触増分を取得できる。これにより、
  初期配置、浮上、着陸に伴う地面接触は評価対象から除外する。Python側の参照実装は
  `hakoniwa-drone-pro/drone_api/external_rpc/fleet_rpc.py`の`FleetRpcController.get_status()`と、
  `hakoniwa-drone-pro/drone_api/pymavlink/env_api_test.py`のbaseline／差分計算である。
- `collided_counts`は高水準の「事故回数」ではなく、新規contact geom pairの累積数である。また相手の
  geom名やCityGML feature IDを含まないため、建物と地面を分類できない。指標名は`City World接触増分`
  とし、合計増分、増分が1以上の機体数、最大機体別増分を保存する。実行途中でcounterが減少した場合は
  resetとして扱い、単純差分を有効値として報告しない。
- 上記は静的確認であり、座標符号、chunk再構成、イベント消費タイミング、200機時の処理時間は
  runtimeで未確認である。今日はシミュレーションを起動せず、次回AWARD-0で確認する。

## Task AWARD-1: Reproducible Wind Scenario

- [x] Wind Scenario v1のschemaとvalidatorを追加する
- [x] イベント時刻、風速、流れる方向、enabledを定義する
- [x] seedと機体別固定倍率を定義する
- [x] Global Wind Assetで箱庭仮想時刻に従って再生する
- [ ] resetでシナリオ先頭と現在風を正しく再適用する
- [x] ScenarioとManual／Liveの排他または優先順位を定義する
- [x] 同じScenarioとseedから同じ機体別風入力列が得られることをテストする
- [x] Scenario hashをReceiptへ保存する

## Task AWARD-2: Rehearsal Observer

- [ ] Show IRから各評価時刻の計画位置を解決する
- [ ] Visual Stateから各機体の実位置を取得する
- [ ] RMS、P95、最大位置誤差をオンライン集計する
- [ ] 許容距離付きFormation成立率を集計する
- [x] 全機takeoff完了後・Show IR開始直前に各機体の`DroneStatus.collided_counts`をbaselineとして保存する
- [x] 最後のhold完了後・land開始前の値との差分からCity World接触増分と接触機体数を集計する
- [x] counter減少をresetとして検出し、不正な差分を結果に採用しない
- [x] `summary.json`へ衝突差分の軽量レポートを出力する
- [ ] 200機runtimeでbaseline/finalの全機取得とレポートを確認する
- [ ] 集約値だけの`timeseries.csv`を出力する
- [ ] 未測定指標を0と誤記しない
- [ ] 代表機体または最大誤差機体の軌道比較データを保存する

## Task AWARD-3: Comparison Cases

- [ ] 会場、Show、機体数、観客カメラを固定する
- [ ] 無風Scenarioと突風Scenarioを確定する
- [ ] 少数機で、建物近傍holdと建物方向への定常風により接触増分が再現するPlan Aを調整する
- [ ] Plan Aを意図的な破壊ケースではなく、無風なら成立する候補計画として説明できることを確認する
- [ ] 計画A・無風を実行する
- [ ] 計画A・突風を同一seedで実行する
- [ ] 結果を確認して計画Bの変更理由を決める
- [ ] 計画Bの変更を最大2項目に限定する
- [ ] 計画B・突風を計画Aと同一Scenario／seedで実行する
- [ ] 3ケースの実行条件と結果を保存する
- [ ] 同一観客カメラでA／B画像を保存する
- [ ] 少なくとも一つの指標で、変更理由と整合する改善を確認する

## Task AWARD-4: Rehearsal Report

- [ ] Venue、Show、Environment、Results、Decision、Scopeを含む静的HTMLを生成する
- [ ] 3ケースの比較表を表示する
- [ ] 位置誤差とFormation成立率のグラフを表示する
- [ ] 同一観客カメラのA／B画像を並べる
- [ ] 計画AからBへの変更理由と変更値を表示する
- [ ] PLATEAU、Show、風Scenarioのprovenanceを表示する
- [ ] Git SHA、各hash、seed、評価条件をReceiptとして表示する
- [ ] 気象モデル値と現地観測値を区別する
- [ ] 安全性・運航可否・法令適合性を保証しない旨を表示する
- [ ] READMEから比較の再実行手順を参照できるようにする

## 一日で進める場合の順序

1. 45分: AWARD-0の座標系、性能、接触観測スパイク
2. 90分: AWARD-1の仮想時刻ベース風Scenario
3. 120分: AWARD-2の必須メトリクス
4. 90分: AWARD-4の最小静的HTML
5. 120分: AWARD-3の3ケース実行と計画B調整
6. 30分: 証拠画像、README、表現統一

開発中は少数機で検証し、最終比較だけ目標機体数で実行する。

## 時間不足時に削る順番

1. 最小離隔
2. 接触相手の詳細分類
3. 最大位置誤差
4. HTMLの装飾
5. 画像の自動撮影
6. 3ケースの一括自動運転
7. 200機以外の機体数比較

削らないもの:

- 仮想時刻と固定seedによる同一風入力
- 計画位置と実位置の座標整合性
- A／B比較
- RMS、P95、Formation成立率
- 計画変更理由
- 一枚のRehearsal Report

## 非目標

- CFDおよび建物周辺の都市気流再現
- 安全認証および実機運航可否判定
- Open-Meteo Ensemble対応
- 新しい都市への対応
- LOD1／LOD2の汎用比較
- AR再開発
- 自動衝突回避および自動計画最適化
- 観客可視率の厳密な自動計算
- CityGMLセマンティクスの完全対応
- 実機連携
- 全都市の再テスト
- コア機能のリファクタリング

## 表現規則

- `安全検証`ではなく`物理リハーサル`または`リスクスクリーニング`と表現する
- Open-Meteoは`気象モデル現在推定値`とし、`現地実測値`と表現しない
- 現在の風モデルは`一様風および同一方向の確率的外乱`とし、`都市気流`と表現しない
- Reportは`Safety Report`ではなく`Rehearsal Report`とする
- シミュレーション結果は安全性、運航可否または法令適合性を保証しない

## 最終受入条件

- [ ] 同じScenarioとseedで同一の風入力列を再生成できる
- [ ] Show IRとVisual Stateを同一ENU座標系で比較できる
- [ ] A・突風とB・突風が同一の風入力条件で比較される
- [ ] 3ケースについてRMS、P95、Formation成立率が出力される
- [ ] 計画AからBへの変更理由と変更値が記録される
- [ ] 少なくとも一つの指標で計画変更の効果を説明できる
- [ ] 同一観客カメラのA／B画像が保存される
- [ ] 3ケースが一枚のRehearsal Reportへ並ぶ
- [ ] 実行条件、hash、seed、Git SHAを追跡できる
- [ ] READMEの手順から比較を再実行できる
