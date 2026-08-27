# Global Wind for Virtual Drone Show

## 目的

PLATEAU City上の多数機ドローンショーへ、一定風および突風を低コストで与える。
既存`hakoniwa-envsim`の環境アセットと`hako_msgs/Disturbance`を技術的な基点としつつ、
今回のショーでは空間領域、境界判定、機体位置検索を行わない。

無限に広い一様な風空間を仮定し、ブラウザから届いた1つのGlobal Wind状態を全機の
Disturbance PDUへ展開する。このショー専用アセット、プロトコル、UI、Recipeは
`hakoniwa-drone-show`で管理し、本リポジトリのPROライセンスを適用する。

## 既存資産との関係

`hakoniwa-envsim/src/hakoniwa_envsim/envasset.py`は、各シミュレーション周期で次を行う。

1. 各DroneのPose PDUを読む
2. 現在位置に対して空間検索する
3. 環境プロパティから`hako_msgs/Disturbance`を生成する
4. 各Droneの`disturb` PDUへ書く

これは局所風、温度、気圧、GPS強度などを位置依存で与える汎用環境アセットとして正しい。
一方、最大256機へ同じ風を与えるショー用途では、毎周期のPose読取と空間検索は不要である。

新しいGlobal Wind Assetは、既存実装から次だけを再利用または踏襲する。

- `hako_msgs/Disturbance`および既存の`disturb`チャネル
- Python PDU変換・書込方法
- Launcher管理と`hakopy.usleep()`による箱庭時刻同期
- Drone設定から対象機一覧を解決する方法
- ENU/ROS/Drone内部NED間の座標変換規則

`hakoniwa-envsim`の空間モデルやfastsearchを複製しない。
既存`envasset.py`の`hakopy.usleep()`後にある`time.sleep()`も踏襲しない。今回のruntimeでは
Bridge側が実時間進行を律速するため、Global Wind Assetがreal sleepすると二重待機になる。

## 第一弾のランタイム構成

```text
Browser Wind UI
  └─ manual compass / speed
          │
          │ Global Wind JSON（変更時のみ）
          ▼
Web PDU Bridge
          │
          ▼
Global Wind Command PDU（SHM、ショー全体で1個）
          │
          ▼
Global Wind Asset（hakoniwa-drone-show）
  ├─ Drone-0 Disturbance PDU
  ├─ Drone-1 Disturbance PDU
  ├─ ...
  └─ Drone-N Disturbance PDU
```

ブラウザは機体ごとのDisturbanceを送信しない。Global Wind Assetだけが1つのGlobal Windを
対象全機へfan-outする。

## 最重要条件: 変更時だけ更新する

通常ループは箱庭時刻を止めないため`hakopy.usleep()`を継続し、Global Wind Commandだけを
非blockingに監視する。`time.sleep()`などのreal sleepは行わない。ただし、次の場合に限って
Disturbance PDUを全機へ書く。

- アセット起動後の初期風を配布するとき
- 箱庭reset後に現在の風を再配布するとき
- 受信したGlobal Windの正規化済み物理状態が変化したとき

`sequence`は順序・重複判定に使うが、sequenceだけが進み物理状態が同じ場合は書かない。
風が変わっていない間は、Pose PDUを読まず、空間検索せず、
各DroneのDisturbance PDUも書き直さない。Drone側はSHMに保持された現在のDisturbance値を
継続して物理計算へ利用する。

## Global Wind JSON案

通信形式はPDUの1024-byte固定長byte配列へUTF-8 JSONを格納する。機体別PDUではなく、
既存`DroneShow`ロボットのchannel 2（`global_wind_command`）をショー全体で1つ使用する。
8-byte headerとzero paddingは既存Show Controlの方式を踏襲する。

```json
{
  "schema": "hakoniwa.drone-show/global-wind/v1",
  "publisher_id": "browser-7f3a9c2e",
  "sequence": 12,
  "source": {
    "mode": "manual",
    "provider": null,
    "observed_at": null
  },
  "wind": {
    "enabled": true,
    "vector_ros_m_s": [3.0, -1.0, 0.0],
    "variation": {
      "speed_stddev_m_s": 1.0,
      "seed": 1
    }
  }
}
```

平均風の物理入力は`enabled`と`vector_ros_m_s`とする。`variation.speed_stddev_m_s`は
同じ方向に流れる機体ごとの風速標準偏差で、0なら全機へ平均ベクトルをそのまま配布する。
乱数は`seed`とDrone名から決定的に生成し、reset後も同じ条件を再現する。負の標本は0 m/sへ
制限し、逆方向の風は生成しない。手動UIの方位は風が実際に流れる方向（to）とする。
受信側は有限値、範囲、schema、sequenceを検証してから適用する。

`enabled: false`は風機能を明示的に無効化し、全機へzero vectorを配布する。`enabled: true`かつ
zero vectorは風機能が有効な無風条件を表す。この違いはUI、ログ、Receiptに保持する。

`sequence`は`publisher_id`内で単調増加させる。ブラウザreloadで新しい`publisher_id`になった
場合はsequenceをリセットできる。第一弾で複数ブラウザから操作された場合はlast-writer-winsとし、
画面に現在の送信元を表示する。将来、同時操作が必要になった場合は明示的なcontrol ownershipを
追加する。

## PDU生成と更新効率

対象Drone一覧と各`disturb`チャネルはconfigure時に確定する。Global Wind Asset起動時に、
全Drone分のDisturbanceオブジェクトまたは送信用バッファを前もって生成する。更新時は平均風と
標準偏差から機体ごとの同方向ベクトルを決定し、対象全機へ1回ずつflushする。

実装時にはPython PDU converterが毎回新しいbyte列を返すかを確認し、次のどちらかを選ぶ。

- 安全な第一実装: DroneごとにDisturbanceオブジェクトを保持し、変更時だけserializeする
- 可能なら最適化: 固定レイアウトを確認した上で送信バッファを保持し、風フィールドだけ更新する

未確認のバイナリoffsetへ直接書き込まない。まず変更時限定fan-outで十分な性能を確認する。

## 風の入力モード

### Manual

ブラウザ上で次を直感的に変更する。

- 風の有効・無効
- コンパスによる風が流れる方向（0°=北、90°=東、to）
- 風速（m/s）
- 必要なら鉛直成分（m/s）

UI操作中も同じ値を連続送信せず、確定値が変わった場合だけsequenceを増やして送る。

### Live weather

無料で利用可能な公開気象データから、会場の緯度経度に対応する最新風を取得する。
ブラウザ側にprovider adapterを置き、取得値をManualと同じGlobal Wind JSONへ正規化する。

- [x] Open-Meteoをproviderとして、利用条件・帰属表示・rate limitを確認する
- [x] API keyを使わず、timeoutと障害時の直前値維持を実装する
- [x] UI表示、5分poll、Hakoniwa仮想時刻を分離する
- [x] 値が変化した場合だけGlobal Wind Commandを送る
- [x] Manual／Liveを再起動なしで切り替える
- [x] 会場、平均風速、from/to方位、gust、データ時刻、取得時刻を表示する
- [x] 即時更新ボタンと取得元APIリンクを表示する
- [x] Liveでも機体ごとの標準偏差を変更できる

外部APIのレスポンスやデータを本リポジトリへ恒久保存・再配布する場合は、別途ライセンスを
確認する。

### Reproducible scenario（将来）

Live weatherはデモ時刻によって結果が変わるため、AWARDの比較デモには再現可能な風シナリオも
必要になる。箱庭仮想時刻を基準に「無風 → 定常風 → 突風 → 無風」を再生し、同じShow IRで
結果を比較できる形式を将来追加する。Manual/Liveと同じGlobal Wind JSONを出力するproducerとし、
Global Wind Asset側へ入力モード固有処理を持ち込まない。

## 責務境界

### `hakoniwa-drone-show`

- Global Wind JSON schemaとvalidator
- Global Wind Asset
- PDU定義とWeb Bridge接続
- 対象DroneごとのDisturbance事前生成と変更時fan-out
- Manual/Live切替、コンパス、風速UI
- 外部風provider adapter
- Recipe、Launcher、設定、テスト、利用手順

### `hakoniwa-envsim`

- 既存の位置依存環境アセットを基準実装として維持する
- 空間風、局所風、建物影響などが必要になった場合のOwnerとする
- 今回のGlobal Wind専用コードは追加しない

### `hakoniwa-threejs-drone`

- DroneとLEDの既存描画を維持する
- 風ベクトル表示に汎用Viewer APIが必要な場合だけ最小拡張する
- Global WindのUI、provider、ショー固有プロトコルは追加しない

## Task WND-0: 基準動作の確認

- [x] 既存Three.jsのManual Wind UIとDisturbance送信実装を調査する
- [x] Manual UI → Web PDU Bridge → SHM callbackの疎通経路を追加する
- [x] Global Wind JSONのブラウザ/Python双方のvalidatorと変更判定をテストする
- [ ] `hakoniwa-envsim`の既存風アセットを1機で起動する
- [ ] Disturbanceの座標系と符号を実測で確認する
- [ ] Disturbance PDUを1回だけ書いた後もDroneが同じ風を継続利用することを確認する
- [ ] reset時にDisturbanceが初期化されるタイミングを確認する
- [x] 風有効時のDrone設定`enable_disturbance`を有効化する

## Task WND-1: Global Wind Asset

- [x] Global Wind JSON v1 schemaとvalidatorを追加する
- [x] ショー全体で1つのcommand PDUを追加する
- [x] configureで全Droneの既存`disturb`チャネルを接続する
- [x] 全Drone分のDisturbanceオブジェクトを起動時に生成する
- [x] 初期化、reset、風変更時だけ全Droneへ書く
- [x] 同一sequenceと同一内容では書かない
- [x] `hakopy.usleep()`を維持し、箱庭時刻同期を止めない
- [x] `time.sleep()`などのreal sleepを入れず、Bridgeとの二重律速を避ける
- [x] malformed、NaN、Infinity、範囲外、古いsequenceを拒否する
- [x] `publisher_id`変更時はsequenceをリセットでき、ブラウザreload後も操作できる
- [x] 複数publisherはlast-writer-winsとし、同一publisher内の古いcommandだけを拒否する
- [x] zero windで外乱を解除できるようにする
- [x] `enabled: false`と`enabled: true`のzero windを状態として区別する
- [ ] 128機、200機、可能なら256機で変更時fan-out時間を測定する

### Acceptance Test

- [ ] 無風で既存ショーと同じ軌道を再生できる
- [ ] 風変更1回につき各DroneへのDisturbance書込が1回だけ発生する
- [ ] 風を変えない状態で機体数に比例する毎周期処理が発生しない
- [ ] 標準偏差0では全機が同じ風ベクトルを受ける
- [ ] 標準偏差を設定すると、逆流せず機体ごとに風速がばらつく
- [ ] 風向または風速を変えると、飛行中の全機へ反映される
- [ ] reset後に現在の風が再適用される
- [ ] Global Wind Assetを無効にすると既存City Showがデグレしない

## Task WND-2: Manual Wind UI

- [x] City Viewerへ風パネルを追加する
- [x] コンパスで風が実際に流れる方向（to）を指定し、ROS風ベクトルへ変換できる
- [x] 平均水平風速と機体ごとの風速標準偏差を指定できる
- [ ] 鉛直成分を指定できる
- [x] 有効・無効を切り替えられる
- [x] 変更確定時だけsequenceを増やして送信する
- [ ] 現在値と最終送信時刻を表示する
- [ ] YAMLへ貼り付け可能な初期風設定をコピーできる

## Task WND-3: Live weather

- [x] 候補providerをライセンス、CORS、認証、更新頻度、地点解像度で比較する
- [x] 会場緯度経度から最新風を取得するprovider adapterを追加する
- [x] 取得値をGlobal Wind JSON v1へ正規化する
- [x] 取得周期をprovider制約に合わせ、値が変化した場合だけ送信する
- [x] Manual/LiveをUIで切り替えられる
- [x] provider名、観測地点、観測時刻を表示する
- [x] 通信失敗、欠測、古い観測値の扱いを実装する

## Task WND-4: AWARD比較デモ

- [ ] 無風、定常風、突風の再現可能な条件を定義する
- [ ] 同じ大阪城Show IRを各条件で実行する
- [ ] 計画位置と実位置の偏差を可視化する
- [ ] 最大偏差、復帰時間、Formation成立性を比較する
- [ ] 風条件、仮想時刻、Show Receiptを結果へ記録する
- [ ] 物理PoCであり実機運航の安全保証ではないことを明記する

## 非目標（第一弾）

- Drone位置の読取
- 空間領域、境界、BVH、fastsearch
- 建物による遮蔽、吹き上げ、乱流の自動計算
- Droneごとに異なる風
- ブラウザから機体ごとのDisturbanceを送ること
- 毎シミュレーション周期のDisturbance再書込
- Global Wind Asset内のreal sleep
- `hakoniwa-envsim`の既存環境アセット変更
- 実機飛行の安全性、気象判断、法令適合性の保証
