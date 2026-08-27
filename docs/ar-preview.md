# カメラARプレビュー

## 方式

カメラARはWebXRではなく、背面カメラ映像の上へ透明なThree.js Viewerを重ねます。
Drone位置はVisual State PDU、LEDはShow IRとShow Statusを正本とするため、通常Viewerと
同じショーを表示します。

```text
背面カメラ
  + 透明Three.js（Drone / LED）
  + Show開始 / 編隊方向ガイド / 任意の端末姿勢
```

観客位置は次の順序で決まります。

```text
起動時の端末GPSまたはテスト位置
  → 会場基準の地理ENU
  → venue.heading_degでShow ENUへ変換
```

GPSはAR開始時に一度だけ取得し、継続追跡しません。画面はYAMLの初期設定でそのまま
表示され、常設の設定パネルはありません。編隊が視野外なら画面端の矢印で案内し、
視野内では鑑賞を妨げる中央マーカーを表示しません。左上の距離ボタンで現在の観客位置
から編隊中心までの直線距離を表示・非表示できます。左下には初期位置からの相対移動、
地面からの高さ、最寄り機までの距離を表示します。GPS誤差と方向案内は
表示確認用であり、実機運航の安全判断には利用しません。

## 設定

```yaml
ar:
  enabled: true
  venue:
    latitude: 35.0988
    longitude: 138.8587
    heading_deg: 0.0
  preview:
    location_source: device
    override:
      latitude: 35.0985305
      longitude: 138.8587
    eye_height_m: 1.6
    movement_speed_m_s: 5.0
    device_orientation: optional
```

- `device`: 端末の現在地を一度取得します。失敗時は`override`へfallbackします。
- `override`: 設定したテスト位置を使います。福井から静岡会場を試す場合に使用します。
- `heading_deg`: 地理的なEast/NorthとShow IRのENUを対応付ける会場方位です。
- `eye_height_m`: 平面床から観客カメラまでの高さです。
- `movement_speed_m_s`: 仮想移動ボタンを押している間の移動速度です。
- `device_orientation`: `optional`ならAR開始時に端末姿勢の利用許可を求め、yaw/pitchへ反映します。端末を上へ向けると視点も上を向き、編隊が遠いほど手ぶれ補正を強くします。`off`は無効です。

## HTTPSの準備

`configure`はworkspaceにローカルCAとサーバー証明書を生成します。CA秘密鍵とサーバー
秘密鍵は生成workspaceだけに置かれ、リポジトリへ保存されません。

```text
work/recipes/drone-fleet-single-host/
  ar-tls/
    hakoniwa-ar-ca.crt
    hakoniwa-ar-ca.key
    hakoniwa-ar-server.crt
    hakoniwa-ar-server.key
  viewer-access/
    ar-viewer-url.txt
    ar-viewer-qr.svg
    ar-ca-install-qr.svg
    hakoniwa-ar-ca.crt
```

iPhoneへ`hakoniwa-ar-ca.crt`をAirDrop等で渡してプロファイルをインストールし、証明書信頼
設定で明示的に信頼します。同じCAは再configureでも再利用されます。MacのLAN IPを変更
した場合は、そのCAを維持したままIP用サーバー証明書だけが再生成されます。

```bash
python3 tools/recipe/virtual_drone_show.py configure
python3 tools/recipe/virtual_drone_show.py doctor
python3 tools/recipe/virtual_drone_show.py start
python3 tools/recipe/virtual_drone_show.py open-ar
```

AR URLは`https://<Mac LAN IP>:8443/drone-show/ar/index.html`、PDU接続は同一オリジンの
`wss://<Mac LAN IP>:8443/pdu`です。GatewayはWSSを既存WebBridgeの
`127.0.0.1:8765`へ中継します。診断・互換用として`wss://<Mac LAN IP>:8766`も維持します。

## 操作

- 「カメラARを開始」: カメラ、初期位置、任意の端末姿勢をまとめて準備します。
- 方向矢印: 編隊が視野外にあるとき、iPhoneを向ける方向を画面端に表示します。
- 左上の「距離」: 編隊中心までの距離表示を切り替えます。
- 左下の位置表示: 初期視点基準の前後左右、地面からの高さ、最寄り機までの距離です。
- 「ドローンショー開始」: 全機表示とRunner待機を確認後に有効になります。
- 右下の「移動」: 必要な時だけ前後左右・上下の半透明ボタンを開きます。
- 1本指ドラッグ / ピンチ: `device_orientation: off`時のyaw/pitch / FOV調整です。

福井など会場外から静岡会場の見え方を試す場合は、画面操作ではなくYAMLを
`location_source: override`へ変更して`configure`し直します。
