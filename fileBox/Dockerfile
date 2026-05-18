# 1. Using the recommended slim image (Debian-based)
FROM python:3.13-slim

# 2. Python environment optimizations
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Set the working directory first
WORKDIR /app

# 4. Merged System Dependencies (Fixed duplicate apt-get step)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# 5. Create a secure, non-root user (Using proper Debian syntax)
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

# 6. Copy requirements.txt first to take advantage of Docker caching
COPY requirements.txt ./

# 7. Install Python packages without saving heavy files to the cache folder
RUN pip install --no-cache-dir -r requirements.txt

# 8. Copy the rest of your project files into the container
COPY . .

# 9. Fix Permissions: Ensure the non-root 'app' user owns all the project files
RUN chown -R app:app /app

# 10. Switch to the secure non-root user (Everything after this runs safely as 'app')
USER app

# 11. Tell Docker your Django application will listen on port 8000
EXPOSE 8000

# 12. Run using 'python -m gunicorn' to safely bypass non-root PATH restrictions
CMD ["python", "-m", "gunicorn", "fileBox.wsgi:application", "--bind", "0.0.0.0:8000"]