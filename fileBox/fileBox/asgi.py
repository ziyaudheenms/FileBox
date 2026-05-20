import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter,URLRouter

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fileBox.settings')

django.setup() # this setup is used to make the django project start working before gettng into the asgi routings so that to solve the classic docker error of "Apps aren't loaded yet."

from .ws_middleware import ClerkAuthMiddleware
from .routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    'http' : get_asgi_application(),
    'websocket' : ClerkAuthMiddleware(URLRouter(websocket_urlpatterns)),
})
