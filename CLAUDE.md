# Video Material Generator - CLAUDE.md

## プロジェクト概要

動画をアップロードすると、音声文字起こし＋画面OCRを統合し、画像付きのHTML教材を自動生成するシステム。
将来的にDocker化してSaaS化・パッケージ販売を想定。

## 技術スタック

- **言語**: Python 3.11+
- **フレームワーク**: FastAPI
- **タスクキュー**: Celery + Redis
- **DB**: PostgreSQL
- **ファイルストレージ**: ローカル（S3互換に差し替え可能な設計）
- **GPU処理**:
  - faster-whisper (large-v3) - 音声文字起こし
  - Surya OCR - 画面テキスト抽出
  - ffmpeg - 動画処理
- **要約**: Claude API (anthropic SDK)
- **コンテナ**: Docker / Docker Compose
- **GPU環境**: NVIDIA RTX 3090 (24GB VRAM), Driver 580.x, CUDA 13.0対応

## ディレクトリ構成

```
video-material-generator/
├── CLAUDE.md                    # このファイル
├── docker-compose.yml
├── Dockerfile
├── Dockerfile.worker            # GPU用ワーカー
├── requirements.txt
├── .env.example
│
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPIアプリケーション
│   ├── config.py                # 設定管理
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py            # APIエンドポイント定義
│   │   └── schemas.py           # Pydanticモデル
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── video_processor.py   # ffmpegによる前処理
│   │   ├── transcriber.py       # faster-whisper音声文字起こし
│   │   ├── ocr_processor.py     # Surya OCR処理
│   │   ├── integrator.py        # タイムスタンプ統合
│   │   ├── summarizer.py        # Claude API要約生成
│   │   └── html_generator.py    # HTML教材生成
│   │
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── celery_app.py        # Celery設定
│   │   └── tasks.py             # 非同期タスク定義
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── job.py               # SQLAlchemyモデル
│   │
│   ├── templates/
│   │   └── material.html        # Jinja2 HTML教材テンプレート
│   │
│   └── utils/
│       ├── __init__.py
│       ├── file_manager.py      # ファイルパス管理
│       └── logger.py            # ロギング設定
│
├── storage/                     # 処理ファイル保存先（Docker volumeマウント）
│   ├── input/                   # アップロード動画
│   ├── processing/              # 処理中ファイル
│   ├── output/                  # 完成教材
│   └── models/                  # AIモデルファイル（永続化）
│
└── tests/
    ├── __init__.py
    ├── test_video_processor.py
    ├── test_transcriber.py
    ├── test_ocr_processor.py
    └── test_integration.py
```

## 処理パイプライン

```
1. 動画アップロード or フォルダ監視で検知
2. ffmpeg: 音声抽出(.wav 16kHz mono) + キーフレーム抽出(シーン検出+重複除去)
3. GPU並列処理:
   a. faster-whisper large-v3 → タイムスタンプ付き文字起こし (~4-6GB VRAM)
   b. Surya OCR → 各フレームの画面テキスト抽出 (~2-3GB VRAM)
4. タイムスタンプで音声テキストと画面テキストを統合
5. Claude API でチャプターごとの要約生成
6. HTML教材生成（画像Base64埋め込み、目次付き、書き起こし折りたたみ）
7. 出力フォルダに配置 + 通知
```

## APIエンドポイント

```
POST   /api/upload              動画アップロード → ジョブID返却
GET    /api/jobs/{job_id}        処理状況確認（status, progress, step）
GET    /api/jobs/{job_id}/result 完成教材取得（HTML, メタデータ）
GET    /api/jobs                 ジョブ一覧
DELETE /api/jobs/{job_id}        ジョブ削除
GET    /api/health               ヘルスチェック
```

## API レスポンス例

### POST /api/upload
```json
{
  "job_id": "uuid-xxxx",
  "status": "queued",
  "created_at": "2026-02-04T12:00:00Z"
}
```

### GET /api/jobs/{job_id}
```json
{
  "job_id": "uuid-xxxx",
  "status": "processing",
  "progress": 65,
  "step": "ocr",
  "steps": {
    "extract_audio": "completed",
    "extract_frames": "completed",
    "transcribe": "completed",
    "ocr": "processing",
    "integrate": "pending",
    "summarize": "pending",
    "generate_html": "pending"
  },
  "created_at": "2026-02-04T12:00:00Z"
}
```

### GET /api/jobs/{job_id}/result
```json
{
  "job_id": "uuid-xxxx",
  "status": "completed",
  "html_url": "/api/jobs/uuid-xxxx/download/html",
  "metadata": {
    "title": "動画タイトル",
    "duration": "02:03:45",
    "chapters": 24,
    "total_frames": 87,
    "word_count": 15234
  }
}
```

## 統合データ構造 (unified_transcript.json)

```json
{
  "metadata": {
    "source_file": "video.mp4",
    "duration": 7425.3,
    "total_frames_extracted": 87,
    "processing_time": 1234.5
  },
  "chapters": [
    {
      "index": 0,
      "timestamp_start": 205.0,
      "timestamp_end": 492.0,
      "timestamp_display": "00:03:25",
      "frame_image": "frames/slide_0325.jpg",
      "frame_image_base64": "data:image/jpeg;base64,...",
      "ocr_text": "市場規模の推移 2020-2024",
      "speech_segments": [
        {
          "start": 205.0,
          "end": 210.5,
          "text": "このグラフを見ていただくと"
        },
        {
          "start": 210.5,
          "end": 218.3,
          "text": "2022年から急激に成長していることがわかります"
        }
      ],
      "speech_text": "このグラフを見ていただくと、2022年から急激に成長していることがわかります...",
      "summary": ""
    }
  ]
}
```

## HTML教材テンプレート仕様

- 単一HTMLファイル（画像はBase64埋め込み）
- レスポンシブ対応
- 目次（各チャプターへのアンカーリンク）
- 各チャプター:
  - タイムスタンプ表示
  - スライド画像表示
  - 要約テキスト
  - `<details>`タグで書き起こし全文を折りたたみ
  - 画面OCRテキスト表示
- 印刷用CSS（PDF変換用）
- ダークモード対応（optional）

## 各コンポーネントの実装詳細

### video_processor.py (ffmpeg処理)
```python
# 音声抽出
# ffmpeg -i input.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 output.wav

# キーフレーム抽出（シーン検出）
# ffmpeg -i input.mp4 -vf "select='gt(scene,0.3)',showinfo" -vsync vfr frames/frame_%04d.jpg
# ファイル名にタイムスタンプを含める

# 重複フレーム除去
# imagehash (phash) で類似フレームを除去
# 閾値: hamming distance < 5 で同一とみなす
```

### transcriber.py (faster-whisper)
```python
# モデル: large-v3
# compute_type: float16 (3090最適)
# VADフィルター: 有効（無音スキップ）
# language: "ja" (日本語固定、auto検出も可)
# 出力: セグメント単位でタイムスタンプ付きテキスト
```

### ocr_processor.py (Surya OCR)
```python
# GPU利用
# 各キーフレームに対してOCR実行
# 出力: フレームファイル名 + タイムスタンプ + 抽出テキスト
# バッチ処理で効率化
```

### integrator.py (タイムスタンプ統合)
```python
# 各フレームのタイムスタンプを基準にチャプター区切り
# フレームN のタイムスタンプ ～ フレームN+1 のタイムスタンプ間の音声セグメントを紐付け
# 統合JSONを生成
```

### summarizer.py (Claude API)
```python
# anthropic SDK使用
# モデル: claude-sonnet-4-20250514
# 各チャプターのspeech_text + ocr_text を入力
# チャプター要約 + 全体要約を生成
# Map-Reduce: 長すぎる場合は分割要約 → 統合
```

### html_generator.py
```python
# Jinja2テンプレートエンジン使用
# 画像をBase64エンコードして埋め込み
# 目次自動生成
# レスポンシブCSS
```

## フォルダ監視モード

```python
# watchdog ライブラリでinputフォルダを監視
# 新規ファイル検知 → Celeryタスクキューに投入
# 対応形式: .mp4, .mov, .avi, .mkv, .webm
# 処理開始時にprocessing/に移動
# 完了時にdone/に移動
```

## 環境変数 (.env)

```
# API
API_HOST=0.0.0.0
API_PORT=8000

# Redis
REDIS_URL=redis://redis:6379/0

# PostgreSQL
DATABASE_URL=postgresql://user:pass@postgres:5432/video_material

# Claude API
ANTHROPIC_API_KEY=sk-ant-xxxxx
CLAUDE_MODEL=claude-sonnet-4-20250514

# Storage
STORAGE_BASE_PATH=/app/storage
INPUT_DIR=/app/storage/input
OUTPUT_DIR=/app/storage/output

# GPU
WHISPER_MODEL=large-v3
WHISPER_COMPUTE_TYPE=float16
WHISPER_LANGUAGE=ja

# Processing
SCENE_DETECT_THRESHOLD=0.3
PHASH_THRESHOLD=5
MAX_CONCURRENT_JOBS=2
```

## Docker構成

### docker-compose.yml
```yaml
services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - storage:/app/storage
    depends_on:
      - redis
      - postgres
    env_file: .env

  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    volumes:
      - storage:/app/storage
      - models:/app/models
    depends_on:
      - redis
      - postgres
    env_file: .env

  redis:
    image: redis:7-alpine

  postgres:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: video_material
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass

volumes:
  storage:
  models:
  pgdata:
```

### Dockerfile.worker (GPU用)
```dockerfile
FROM nvidia/cuda:12.4-runtime-ubuntu22.04
# Python 3.11, ffmpeg, PyTorch (CUDA 12.4), faster-whisper, surya-ocr, imagehash
# モデルファイルは /app/models にマウント（初回起動時にダウンロード）
```

## 開発の進め方

### Phase 1: コア処理（MVP）
1. FastAPIの基本構成（ヘルスチェック、アップロード）
2. video_processor.py（ffmpeg音声抽出 + キーフレーム抽出）
3. transcriber.py（faster-whisper）
4. ocr_processor.py（Surya OCR）
5. integrator.py（タイムスタンプ統合）
6. summarizer.py（Claude API）
7. html_generator.py（Jinja2テンプレート）
8. 同期的にパイプライン全体を通す

### Phase 2: 非同期化 + Docker化
1. Celery + Redis でタスクキュー化
2. ジョブ管理（PostgreSQL）
3. Docker Compose構成
4. フォルダ監視モード（watchdog）

### Phase 3: SaaS機能
1. 認証（APIキー or JWT）
2. マルチテナント
3. 課金（Stripe連携）
4. 管理画面

## コーディング規約

- 型ヒント必須
- docstring必須（Google style）
- asyncは FastAPI のエンドポイントのみ、Celeryタスクは同期
- ログは structlog でJSON形式
- エラーハンドリングは各処理層で適切にキャッチしてログ出力
- テストは pytest
