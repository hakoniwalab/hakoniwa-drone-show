# BodyFrame Fleet Recording: 128 UAV / 8 processes

`bodyframe-fleet-recording-128.yaml` は、Business Pack の Fleet 性能測定で選択した
128機・8プロセスの条件を、ブラウザから開始できる実時間デモとして実行するRecipeです。
各プロセスは16機を担当します。

このRecipeは `BodyFrame` を使用します。MuJoCoの物理World、MJCF、City環境は生成せず、
BodyFrame Fleetの位置・速度計算とThree.js表示だけを使用します。開始ボタンはシナリオの
開始時刻だけを遅らせるため、`HAKONIWA` Formationのパラメータは性能測定条件と同一です。

## 前提

次のリポジトリを同じ親ディレクトリに配置し、Business PackのFoundationを構築済みにします。

```text
business-pack/
  hakoniwa-business-pack/
  hakoniwa-drone-core/
  hakoniwa-drone-show/
  hakoniwa-threejs-drone/
```

既定の配置と異なる場合は、`HAKONIWA_BUSINESS_PACK_ROOT`、`--drone-root`、
`--viewer-root`で明示します。

## 準備と構成生成

`hakoniwa-drone-show`で実行します。

```bash
python3 tools/recipe/bodyframe_fleet_recording.py prepare-native
python3 tools/recipe/bodyframe_fleet_recording.py prepare-viewer
python3 tools/recipe/bodyframe_fleet_recording.py configure
python3 tools/recipe/bodyframe_fleet_recording.py doctor
```

生成先はBusiness Packの通常Fleet workspaceとは別の、
`work/recipes/drone-fleet-bodyframe-recording/`です。既存の性能測定workspaceや、
MuJoCo Drone Show workspaceを上書きしません。

## 開始と録画

まずLauncherを開始します。

```bash
python3 tools/recipe/bodyframe_fleet_recording.py start
```

Launcherが起動した後、別ターミナルからViewerを開きます。

```bash
python3 tools/recipe/bodyframe_fleet_recording.py open-viewer
```

自動で開かない環境では、ブラウザで次を開きます。

```text
http://127.0.0.1:8000/recording/index.html
```

画面が128機の表示を準備し、`Waiting for START` と表示されたら `Start show` を押します。
Show Runnerがその操作を受けてから、実時間同期でシナリオを開始します。録画を開始する
タイミングをこの待機中に合わせられます。

## 停止と再構成

終了時はRecipe経由でLauncherを停止します。

```bash
python3 tools/recipe/bodyframe_fleet_recording.py stop
python3 tools/recipe/bodyframe_fleet_recording.py status
```

`configure`は実行中のsessionには重ねられません。パラメータを変更して再構成する場合も、
先に`stop`で終了し、`status`が`TERMINATED`であることを確認してください。

この録画Recipeは、再現性を保つため128機・8プロセス以外の`--drone-count`および
`--process-count`を受け付けません。
