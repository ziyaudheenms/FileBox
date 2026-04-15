# FileBox: Enterprise Cloud Storage Platform

FileBox is a high-performance, full-stack cloud storage solution designed for speed, security, and scalability. It combines a sleek Next.js frontend with a robust Django DRF backend, optimized with Redis caching and Celery background workers.

## 🛠️ Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Frontend | Next.js, Tailwind CSS | Server-side rendering & Fluid UI |
| Backend | Django REST Framework (DRF) | Scalable API & Complex Logic |
| Auth | Clerk | Identity management & Secure JWT session |
| Task Queue | Celery + Redis | Asynchronous file processing |
| Caching | Redis | High-speed data retrieval & Rate limiting |
| Database | PostgreSQL | Relational data integrity |

## ✨ Key Features

### 📂 Advanced File Management
- Hierarchical folder organization with nested structures
- Smart search & filters by name, type, or metadata
- Contextual actions (trash, favorite, details)
- Grid and List view toggling

### ⚡ Performance & Scalability
- Asynchronous file processing via Celery
- Intelligent Redis caching for directory lookups
- Rate limiting protection against abuse
- Optimized queries (select_related/prefetch_related)

### 📊 Storage Intelligence
- Real-time storage visualization by category
- Accurate usage tracking (free vs. used space)
- Recent activity quick-access panel

## 🏗️ Backend Architecture
- Clean Architecture pattern with security focus
- Atomic operations using F() expressions
- Guard Clause API validation for fail-fast approach
- Background workers for auto-deletion, thumbnails, quota recalculation

## 🛡️ Security
- JWT validation via Clerk's secure SDK
- Owner-based access control with strict guest filtering
- Link expiration and password-protected sharing support

## 📁 Project Structure

```
filebox-backend/
├── readme.md                 # Project overview & setup
├── readme.py               # Quick README viewer
├── requirements.txt
├── manage.py
├── db.sqlite3
├── fileBox/                # Django project settings
│   ├── settings.py
│   ├── asgi.py
│   ├── wsgi.py
│   ├── celery.py
│   ├── urls.py
│   ├── routing.py
│   ├── consumers.py
│   ├── ws_middleware.py
│   └── exceptions.py
├── apis/                   # API layer
│   └── v1/                # Versioned APIs
│       ├── auth/          # Authentication endpoints
│       └── filebox/       # File APIs
│           ├── serializers.py
│           ├── views.py
│           └── pagination.py
├── Backend/               # Core Django app
│   ├── models.py
│   ├── views.py
│   ├── tasks.py
│   ├── tests.py
│   ├── admin.py
│   ├── ratelimit.py
│   └── migrations/
├── joined_files/          # Storage runtime data
├── temp_chunks/           # Temporary file chunks
└── ...
```


## 🔧 Installation & Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- Redis Server

### Backend Setup
```bash
git clone https://github.com/yourusername/filebox-backend.git
pip install -r requirements.txt
redis-server
celery -A core worker -l info
python manage.py migrate
python manage.py runserver
```


