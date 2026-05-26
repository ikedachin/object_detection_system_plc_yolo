# 🚧 **under construction** 👷‍♀️
# YOLOシステム
ultralytics社のYOLOを**誰でも、簡単に**使えることを目的としたwebアプリです
YOLOに関してはultralytics社のライセンスに準じます。



## 概要

このプロジェクトは、Webカメラを使用して物体検出を行います。
たとえば部屋の中の写真を定期的に撮影し、人やペット、お皿などにアノテーションを施し、学習することで機械学習（YOLO）を用いてアイテムを推論（検出）するシステムです。

## 主な機能
- **自動画像キャプチャ**: 設定された時間間隔で自動的に画像をキャプチャして保存
- **手動スナップショット**: ユーザーが必要なときに手動でスナップショットを撮影
- **画像の切り取り**：学習データの写真を大きめの画像サイズで撮影し、切り取る位置を決めて全データに適用することができます。
- **学習**：学習時のパラメータを簡単にセットすることができます。詳しくはultralytics社のHPを見てください。
- **アイテム推論（検出）**: YOLOモデルを使用した箱内のアイテム推論（検出）


## システム構成

### バックエンド

- **Django**: ウェブアプリケーションフレームワーク
- **Channels/Daphne**: WebSocketサポート用
- **OpenCV**: カメラ制御と画像処理
- **Ultralytics YOLO**: 物体検出と分類

### フロントエンド

- **HTML/CSS/JavaScript**: ユーザーインターフェース
- **WebSocket**: リアルタイムデータ通信


## フォルダ構成
```
yolo_system/
├── detect/ # 推論結果保存先（日付フォルダと時間フォルダの中に結果が格納されます）
│   ├── 20250724/
│   │   ├── 22_30_18/
│   │   │   └── predict/
│   │   ├── 22_30_22/
│   │   │   └── predict/
│   │   └── ...
├── projects/ # プロジェクト別にフォルダを分けます。画像自動キャプチャ時にプロジェクト名が決まります。
│   ├── project_20250724_222419/
│   │   ├── annotated/ # 学習用データ
│   │   │   └── data_collection/
│   │   ├── cropped/ # 切り取りデータ
│   │   ├── data_collection/ # 自動収集されたデータ
│   │   │   ├── snap_2025-07-24_22-24-25.jpg
│   │   │   └── ...
│   │   ├── models/ # 学習後に出力されるモデルや学習結果
│   │   │   └── ...
│   │   └── thumbnail/ webアプリ表示用サムネイル
│   │       └── ...
├── settings/ # 残骸かも・・・
│   └── yolo_detect.yaml
├── yolo_system/ # Djangoのファイル
│   ├── annotator/ # アノテーションを行うアプリ
│   │   └── ...
│   ├── checker/ # 推論を行うアプリ
│   │   └── ...
│   ├── configuration/ # 設定・プロジェクト管理を行うアプリ
│   │   └── ...
│   ├── crop_app/ # 画像切り取り位置を決定し、切り取るアプリ
│   │   └── ...
│   ├── get_imgs/ # 学習用データとなる画像を収集するアプリ
│   │   └── ...
│   ├── training/ # 学習を実行するアプリ
│   │   └── ...
│   ├── yolo_system/
│   │   ├── __init__.py
│   │   ├── asgi.py
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── wsgi.py
│   │   └── ...
│   ├── (db.sqlite3) # データベース
│   ├── manage.py
│   └── (yolo11n.pt) # yoloのウエイト
├── design_docs/ # 設計書を入れておく予定（作成中）
│   ├── project_folder_construction.md
│   └── ...
├── pyproject.toml
├── README.md
├── start.sh # ワンタッチ実行用のシェルスクリプト（作成中）
├── TASK_FOLDER_STRUCTURE.md
├── uv.lock
```



## Djangoアプリケーションの機能詳細


`yolo_system` ディレクトリ配下には、以下の主要なDjangoアプリケーションモジュールがあります：

### 1. チェッカーアプリ (`checker`)
出荷用の箱内アイテムを推論（検出）するアプリです。
- キャプチャ画像内のアイテム推論（YOLO推論）
- 推論結果のビジュアル表示
- 推論インターフェース（Web UI）
- 共有カメラリソースによる効率的な画像処理
- 結果の保存・履歴管理

### 2. 画像取得アプリ (`get_imgs`)
カメラからの画像取得・保存・配信を担当するアプリです。
- WebSocketによるリアルタイムカメラフィード配信
- 自動画像キャプチャ（インターバル撮影）
- 手動スナップショット取得
- 画像保存・管理（自動/手動）
- マルチスレッドによるカメラ制御


### 3. 設定アプリ (`configuration`)
システム全体の設定管理を提供するアプリです。
- 設定ファイル（YAML等）の管理・編集
- システム全体のパラメータ管理

### 4. 画像切り抜きアプリ (`crop`)
画像の切り抜き・前処理専用のアプリです。
- インタラクティブな画像切り抜きUI
- バッチ切り抜き・YAML出力
- EXIF対応・セキュリティ対策
- 切り抜き座標の一括管理・ダウンロード

### 5. 学習管理アプリ (`training`) ※作成中
YOLOモデルの学習・管理を行うアプリです（開発中）。
- 学習ジョブの管理・実行
- 学習状況の可視化・履歴管理
- モデルファイルの管理

### 6. 推論アプリ (`checker`)
学習したモデルを用いる

### 7. その他・共通モジュール
（必要に応じて追加されることがあります）
- 共通ユーティリティ、ミドルウェア、管理用コマンド等

### 4. メイン設定・ルーティング (`yolo_system`)
Djangoプロジェクト本体の設定・ルーティング・ASGI/WGIエントリポイントを管理します。
- プロジェクト全体の設定（settings.py）
- URLルーティング（urls.py）
- ASGI/WGIサーバー起動用ファイル

### 5. その他・共通モジュール
（必要に応じて追加されることがあります）

## セットアップと実行方法

### 作成環境

- Python 3.11（他バージョンは未確認）
おそらく多くのpythonのバージョンで動くはず
- 必要なパッケージ:
  - channels >= 4.2.2
  - daphne >= 4.2.0
  - django >= 5.2.2
  - ipykernel >= 6.29.5 (Jupyter Notebook用)
  - opencv-python >= 4.11.0.86
  - pip >= 25.1.1
  - pyyaml >= 6.0.2
  - ultralytics >= 8.3.158
  あまりバージョンを気にしなくていいかもしれない

### インストール
1. リポジトリをクローンする
2. 依存関係をインストール
   - uvを使う場合
      ```bash
      uv sync
      ```
   - venvを使う場合
      ```bash
      python3 -m venv .venv
      source .venv/bin/activate
      pip install -r requirements.txt
      ```

### データベース構築
   - uvを使う場合
      ```bash
      cd yolo_system
      uv run python manage.py makemigrations
      uv run python manage.py migrate
      ```
   - venvを使う場合
      ```bash
      source .venv/bin/activate
      cd yolo_system
      python manage.py makemigrations
      python manage.py migrate
      ```


### 実行

Djangoサーバーを起動:
   - uvを使う場合
      ```bash
      cd yolo_system
      uv run python manage.py runserver
      ```


   - uvを使う場合
      ```bash
      source .venv/bin/activate
      cd yolo_system
      python manage.py runserver
      ```

   - または、提供されているスクリプトを使用:(作成中)
      ```bash
      ./start.sh
      ```

### Webアプリへのアクセス
   - サーバー起動後、ブラウザで次のURLにアクセスしてください：
      ```
      http://localhost:8000
      ```
### License
MITライセンスとして公開します。
ただし、本プログラム内で利用しているUltralytics YOLOはAGPLv3ライセンスです。YOLOの使用に関しては、Ultralytics社のライセンス条件に従ってください。

