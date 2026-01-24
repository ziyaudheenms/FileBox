import os
from channels.routing import ProtocolTypeRouter,URLRouter
from django.core.asgi import get_asgi_application
from .ws_middleware import ClerkAuthMiddleware

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fileBox.settings')

from .routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    'http' : get_asgi_application(),
    'websocket' : ClerkAuthMiddleware(URLRouter(websocket_urlpatterns)),
})
