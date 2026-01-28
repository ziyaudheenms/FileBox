"""
Docstring for fileBox.fileBox.ws_middleware

This module contains middleware and utility functions for handling WebSocket connections
and integrating them with Django's ORM in an asynchronous context.

For Creating custom rooms for each user we need there auth details from the scope of the consumer.
Since it's integrated with Clerk , we cant directly use the defalut AuthMiddleWareStack provided by channels.
So we create a custom middleware to extract the auth details from the scope and attach the user object to the scope.

"""
import os
from wsgiref import headers
from dotenv import load_dotenv
from channels.db import database_sync_to_async
import httpx
from Backend.models import ClerkUserProfile
from clerk_backend_api import Clerk
from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions
from django.contrib.auth.models import AnonymousUser
load_dotenv()
clerk_SDK = Clerk(bearer_auth=os.getenv("CLERK_API_KEY"))  

@database_sync_to_async
def get_the_clerk_user(user_id: str):
    try:
        print("collected the user DATABASE RECORD")
        clerk_user = ClerkUserProfile.objects.get(clerk_user_id=user_id)
        return clerk_user
    except ClerkUserProfile.DoesNotExist:
        print("Clerk user not found in database for user_id:", user_id)
        return AnonymousUser()


class ClerkAuthMiddleware:
    def __init__(self , inner):
        self.inner = inner
    
    async def __call__(self , scope ,receive, send):
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = dict(qp.split("=") for qp in query_string.split("&") if "=" in qp)
        token = query_params.get("token")
        print(token)
        if token:
            # Simulate an HTTP request to authenticate the token since the web socket scope does not have headers
            headers = {"Authorization": f"Bearer {token}"}
            mock_request = httpx.Request("GET", "http://localhost:3000", headers=headers) 
            request_state = clerk_SDK.authenticate_request(
                mock_request,
                AuthenticateRequestOptions(
                    authorized_parties=['http://localhost:3000']
                )
            )
            if request_state.is_signed_in:
                print("Middleware Authenticated Successfully")
                request_payload = request_state.payload
                user_id = request_payload['sub']

                scope['user'] = await get_the_clerk_user(user_id)
                print("User attached to scope:", scope['user'])
                print(scope)
                return await self.inner(scope, receive, send)
            else:
                print("Middleware Authentication Failed")
                scope['user'] = AnonymousUser()
        else:
            print("No token provided in WebSocket connection")
            scope['user'] = AnonymousUser()

        
