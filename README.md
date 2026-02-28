# 🎯 Smart Media Fetcher

> Production-ready Universal Media Downloader — Full-Stack Web Application

---

## 📐 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENT BROWSER                       │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTPS
┌─────────────────────▼───────────────────────────────────────┐
│                    NGINX (Reverse Proxy)                     │
│              Rate Limiting · SSL Termination                 │
└──────┬──────────────────────────────────┬───────────────────┘
       │ /api/*                            │ /*
┌──────▼──────────────┐        ┌──────────▼─────────────┐
│   FastAPI Backend   │        │   Static Frontend       │
│   (Uvicorn/Gunicorn)│        │   HTML + CSS + JS       │
└──────┬──────────────┘        └────────────────────────-┘
       │
┌──────▼──────────┬────────────┬───────────────┐
│   PostgreSQL    │   Redis     │   Celery      │
│   (Database)    │   (Cache)   │   (Workers)   │
└─────────────────┴────────────┴───────────────┘
```

## 🗂️ Folder Structure

```
smart-media-fetcher/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app entry point
│   │   ├── api/routes/             # API route handlers
│   │   ├── core/                   # Config, security, logging
│   │   ├── db/                     # Database models & migrations
│   │   ├── services/               # Business logic (downloaders)
│   │   ├── tasks/                  # Celery background tasks
│   │   ├── schemas/                # Pydantic request/response models
│   │   └── utils/                  # Helpers (SSRF guard, filename, etc.)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── templates/index.html        # Main UI
│   └── static/                     # CSS, JS, assets
├── nginx/
│   └── nginx.conf                  # Production Nginx config
├── scripts/
│   └── setup.sh                    # Ubuntu server setup
├── docs/
│   └── ARCHITECTURE.md
├── docker-compose.yml
├── .env.example
└── README.md
```

## 🚀 Quick Start (Docker)

```bash
# 1. Clone and configure
git clone https://github.com/yourorg/smart-media-fetcher
cd smart-media-fetcher
cp .env.example .env
# Edit .env with your secrets

# 2. Launch all services
docker-compose up -d --build

# 3. Run database migrations
docker-compose exec backend alembic upgrade head

# 4. Access the app
open http://localhost
```

## 🔧 Manual Setup (Ubuntu)

```bash
# Run the automated setup script
chmod +x scripts/setup.sh
sudo ./scripts/setup.sh
```

## 📡 API Endpoints

| Method | Endpoint                  | Description              | Auth     |
|--------|---------------------------|--------------------------|----------|
| POST   | /api/v1/download/analyze  | Analyze URL              | Optional |
| POST   | /api/v1/download/fetch    | Fetch and stream file    | Optional |
| POST   | /api/v1/download/bulk     | Bulk URL processing      | JWT      |
| GET    | /api/v1/history           | User download history    | JWT      |
| POST   | /api/v1/auth/register     | Register user            | —        |
| POST   | /api/v1/auth/login        | Login, get JWT           | —        |
| GET    | /api/v1/keys              | List API keys            | JWT      |
| POST   | /api/v1/keys              | Create API key           | JWT      |

## 🔐 Security Features

- SSRF prevention (block private/internal IP ranges)
- JWT authentication with refresh tokens
- API key system for developers
- Rate limiting per IP and per user
- Strict URL validation
- Filename sanitization
- Path traversal prevention
- Request timeouts on all external calls
- File size limits
- Structured audit logging

## 🗺️ Future Roadmap

1. **Browser Extension** — right-click any media to send to fetcher
2. **Webhook support** — POST to your URL when bulk jobs complete
3. **S3 Storage** — persist files with expiry links
4. **Subscription tiers** — Free / Pro / API plans
5. **Admin dashboard** — usage stats, user management
6. **Media conversion pipeline** — FFmpeg cluster for heavy jobs
7. **CDN integration** — serve converted files from edge
8. **OAuth login** — Google / GitHub login
