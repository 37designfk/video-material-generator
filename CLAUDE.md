# Video Material Generator

動画をアップロードすると、音声文字起こし + 画面OCR を統合し、画像付きのHTML教材を自動生成するシステム。

## クイックスタート

```bash
# Docker起動
docker-compose up -d

# アクセス
http://localhost:8000/  # → ログインページ
```

## 技術スタック

| カテゴリ | 技術 |
|---------|------|
| API | FastAPI + Uvicorn |
| タスクキュー | Celery + Redis |
| DB | SQLite (dev) / PostgreSQL (prod) |
| 認証 | JWT + bcrypt + APIキー |
| GPU処理 | faster-whisper, EasyOCR |
| 動画処理 | ffmpeg |
| AI要約 | Claude API (Anthropic) |
| コンテナ | Docker + NVIDIA Container Toolkit |

## ディレクトリ構成

```
app/
├── main.py              # FastAPIエントリーポイント
├── config.py            # 設定管理
├── api/
│   ├── routes.py        # APIエンドポイント
│   ├── schemas.py       # Pydanticスキーマ
│   ├── auth_routes.py   # 認証エンドポイント
│   ├── auth_schemas.py  # 認証スキーマ
│   └── dependencies.py  # 認証依存関係
├── core/
│   ├── auth.py          # 認証ユーティリティ
│   ├── video_processor.py
│   ├── transcriber.py   # faster-whisper
│   ├── ocr_processor.py # EasyOCR
│   ├── integrator.py
│   ├── summarizer.py    # Claude API
│   └── html_generator.py
├── models/
│   ├── job.py           # Jobモデル
│   └── user.py          # User/APIKeyモデル
├── workers/
│   ├── celery_app.py
│   └── tasks.py
├── static/
│   ├── index.html       # メインUI
│   ├── login.html       # ログイン
│   └── register.html    # 登録
└── utils/
    ├── file_manager.py
    └── logger.py
```

## APIエンドポイント

### 認証
| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/api/auth/register` | ユーザー登録 |
| POST | `/api/auth/login` | ログイン (JWT発行) |
| POST | `/api/auth/logout` | ログアウト |
| GET | `/api/auth/me` | 現在のユーザー情報 |
| POST | `/api/auth/api-keys` | APIキー作成 |
| GET | `/api/auth/api-keys` | APIキー一覧 |
| DELETE | `/api/auth/api-keys/{id}` | APIキー削除 |

### ジョブ管理
| メソッド | パス | 説明 | 認証 |
|---------|------|------|------|
| GET | `/api/health` | ヘルスチェック | 不要 |
| POST | `/api/upload` | 動画アップロード | 必要 |
| GET | `/api/jobs` | ジョブ一覧 | 必要 |
| GET | `/api/jobs/{id}` | ジョブ状態 | 不要 |
| GET | `/api/jobs/{id}/result` | 結果取得 | 不要 |
| GET | `/api/jobs/{id}/download/html` | HTMLダウンロード | 不要 |
| DELETE | `/api/jobs/{id}` | ジョブ削除 | 必要 |

## 認証方式

### Web UI (Cookie認証)
1. `/static/login.html` でログイン
2. サーバーがJWTをHTTP-only Cookieにセット
3. 以降のリクエストはCookieで自動認証

### API (APIキー認証)
```bash
curl -H "Authorization: Bearer vmg_xxxx..." http://localhost:8000/api/jobs
```

## 環境変数 (.env)

```bash
# API
API_HOST=0.0.0.0
API_PORT=8000

# Redis
REDIS_URL=redis://localhost:6379/0

# Database
DATABASE_URL=sqlite:///./storage/video_material.db

# Claude API
ANTHROPIC_API_KEY=sk-ant-xxxxx
CLAUDE_MODEL=claude-sonnet-4-20250514

# Storage
STORAGE_BASE_PATH=./storage
INPUT_DIR=./storage/input
OUTPUT_DIR=./storage/output
PROCESSING_DIR=./storage/processing

# GPU / Whisper
WHISPER_MODEL=large-v3
WHISPER_COMPUTE_TYPE=float16
WHISPER_LANGUAGE=ja

# Processing
SCENE_DETECT_THRESHOLD=0.3
PHASH_THRESHOLD=5
MAX_CONCURRENT_JOBS=2

# Authentication
JWT_SECRET_KEY=your_secure_random_string_here
REQUIRE_AUTH=true
```

## Docker構成

| サービス | ポート | 説明 |
|---------|--------|------|
| api | 8000:8000 | FastAPI |
| worker | - | Celery GPU Worker |
| redis | 6380:6379 | タスクキュー |
| postgres | 5433:5432 | DB (本番用) |

## 処理パイプライン

```
1. 動画アップロード
2. ffmpeg: 音声抽出 + キーフレーム抽出
3. GPU並列処理:
   a. faster-whisper → 文字起こし
   b. EasyOCR → 画面テキスト抽出
4. タイムスタンプ統合
5. Claude API で要約生成
6. HTML教材生成
```

---

## 変更履歴

### v0.3.0 - 2026-02-05
**認証システム追加**
- ユーザー登録・ログイン機能 (JWT + bcrypt)
- APIキー認証 (プログラムアクセス用)
- HTTP-only Cookie でセッション管理
- ログイン・登録ページ追加
- 保護エンドポイントの認証チェック

新規ファイル:
- `app/models/user.py` - User/APIKeyモデル
- `app/core/auth.py` - 認証ユーティリティ
- `app/api/auth_routes.py` - 認証エンドポイント
- `app/api/auth_schemas.py` - 認証スキーマ
- `app/api/dependencies.py` - 認証依存関係
- `app/static/login.html` - ログインページ
- `app/static/register.html` - 登録ページ

依存関係追加: `bcrypt`, `PyJWT`, `email-validator`

### v0.2.1 - 2026-02-05
**Docker修正**
- `requests` パッケージ追加 (faster-whisper依存)
- ポート競合回避: Redis 6380, PostgreSQL 5433

### v0.2.0 - 2026-02-04
**Phase 2: 非同期処理 + Docker化**
- Celery + Redis によるタスクキュー
- Docker Compose 構成
- GPU Worker (NVIDIA CUDA 12.2)
- Web UI (index.html)
- ジョブ管理API
- CUDA 12.4 → 12.2 (PyTorch互換性)
- surya-ocr → EasyOCR (軽量化)
- PostgreSQL → SQLite (開発用)

### v0.1.0 - 2026-02-04
**Phase 1: コア処理 (MVP)**
- FastAPI 基本構成
- video_processor.py (ffmpeg)
- transcriber.py (faster-whisper)
- ocr_processor.py (EasyOCR)
- integrator.py (タイムスタンプ統合)
- summarizer.py (Claude API)
- html_generator.py (Jinja2)
- 同期パイプライン

---

## 開発メモ

### ローカル開発 (Docker外)
```bash
# 仮想環境
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Redis起動
redis-server

# API起動
uvicorn app.main:app --reload

# Worker起動 (別ターミナル)
celery -A app.workers.celery_app worker --loglevel=info -Q gpu
```

### 本番デプロイ
1. `.env` の `JWT_SECRET_KEY` を安全な値に変更
2. HTTPS有効化 (Cloudflare等)
3. `REQUIRE_AUTH=true` 確認
4. PostgreSQL使用推奨
