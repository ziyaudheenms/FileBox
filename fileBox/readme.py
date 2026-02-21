"""
readme.py - quick README viewer for the FileBox backend project

Run this script to print a short project overview and developer setup steps.

Usage:
    python readme.py

This file is intended to complement the existing README.md by providing
copyable commands and a quick reference for contributors.
"""

PROJECT_NAME = "FileBox Backend"
DESCRIPTION = (
    "Django backend for FileBox: file storage, sharing and real-time features."
)

REQUIREMENTS = [
    "Python 3.10+",
    "See requirements.txt for pinned Python packages",
]

SETUP_STEPS = [
    "Create and activate a virtual environment",
    "Install dependencies: pip install -r requirements.txt",
    "Run migrations: python manage.py migrate",
    "Create a superuser: python manage.py createsuperuser",
]

RUNNING = [
    "Run the development server: python manage.py runserver",
    "Start Celery worker (if using async tasks): celery -A fileBox worker -l info",
]

ENV_VARS = [
    "SECRET_KEY - Django secret key",
    "DEBUG - 1 or 0",
    "DATABASE_URL - optional if using non-sqlite DB",
    "CELERY_BROKER_URL - e.g., redis://localhost:6379/0",
]

PROJECT_STRUCTURE = (
    "Top-level important files and folders: db.sqlite3, manage.py, requirements.txt,\n"
    "apis/ (versioned API views and serializers), Backend/ (Django app models/views),\n"
    "fileBox/ (project settings, ASGI, WSGI, celery config), joined_files/, temp_chunks/"
)

EXAMPLES = [
    "Install deps:\n  pip install -r requirements.txt",
    "Migrate:\n  python manage.py migrate",
    "Run server:\n  python manage.py runserver",
]

def build_readme_text():
    parts = []
    parts.append(f"{PROJECT_NAME}\n{'='*len(PROJECT_NAME)}\n")
    parts.append(DESCRIPTION + "\n")
    parts.append("Requirements:\n" + "\n".join(f"- {r}" for r in REQUIREMENTS) + "\n")
    parts.append("Setup Steps:\n" + "\n".join(f"- {s}" for s in SETUP_STEPS) + "\n")
    parts.append("Run (dev):\n" + "\n".join(f"- {r}" for r in RUNNING) + "\n")
    parts.append("Important env vars:\n" + "\n".join(f"- {e}" for e in ENV_VARS) + "\n")
    parts.append("Project structure:\n" + PROJECT_STRUCTURE + "\n")
    parts.append("Quick examples:\n" + "\n".join(f"- {e}" for e in EXAMPLES) + "\n")
    parts.append("Notes:\n- DB is SQLite by default (db.sqlite3).\n- See existing README.md for more details.\n")
    return "\n".join(parts)


def print_readme():
    print(build_readme_text())


if __name__ == '__main__':
    print_readme()
