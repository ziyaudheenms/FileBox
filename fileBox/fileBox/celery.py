# myproject/myproject/celery.py
from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fileBox.settings')

# Create a Celery application instance
app = Celery('fileBox') # Use your project name here

# Load configuration from your Django settings.py file, using the 'CELERY' namespace.
# e.g., CELERY_BROKER_URL will be picked up.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps (looks for tasks.py files)
app.autodiscover_tasks()