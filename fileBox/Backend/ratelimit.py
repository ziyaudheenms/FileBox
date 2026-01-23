import os

from dotenv import load_dotenv
from django.http  import HttpRequest

from clerk_backend_api import Clerk
from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions

from Backend.models import ClerkUserProfile

load_dotenv()
clerk_SDK = Clerk(bearer_auth=os.getenv("CLERK_API_KEY")) 

def get_user_tier_based_rate_limit(group : str, request : HttpRequest):
    #since we are using the clerk for our ultimate authentication , first lets verfiy whether the user is authenticated or not.
    try:
        print("Entered into the rate limit function")
        request_state = clerk_SDK.authenticate_request(
            request,
            AuthenticateRequestOptions(
                authorized_parties=["http://localhost:3000"]
            )
        )
    except Exception as e:
        print("You are in exception block of rate limit function")
        return '5/m'  # default rate limit for unauthenticated users.

    if request_state.is_signed_in:
        print("User is signed in")
        request_payload = request_state.payload
        user_id = request_payload['sub']  # user ID
        #with the user id , tring to fetch the user from our database to check their tier.
        if ClerkUserProfile.objects.filter(clerk_user_id=user_id).exists():
            user_instance = ClerkUserProfile.objects.get(clerk_user_id=user_id)  # collecting the user instance from database.
            user_tier = user_instance.clerk_user_tier #collecting the user tier from the user instance.
            # applying the logic to return the rate limit based on the user tier.
            if user_tier == 'FREE':
                return '10/m'
            elif user_tier == 'PRO':
                return '25/m'
            elif user_tier == 'ADVANCED':
                return '50/m'
        else:
            return '5/m'  # if user not found in our database , applying the default rate limit for unauthenticated users.
    else:
        print("User is not signed in")
        return '5/m'  # default rate limit for unauthenticated users
    


def get_user_role_or_ip(group : str, request : HttpRequest):
    #since we are using the clerk for our ultimate authentication , first lets verfiy whether the user is authenticated or not.
    try:

        request_state = clerk_SDK.authenticate_request(
            request,
            AuthenticateRequestOptions(
                authorized_parties=["http://localhost:3000"]
            )
        )
    except Exception as e:
        print("You are in exception block of rate limit function")
        return 'ip'  # default rate limit for unauthenticated users.

    if request_state.is_signed_in:
        request_payload = request_state.payload
        user_id = request_payload['sub']  # user ID
        #with the user id , tring to fetch the user from our database to check their tier.
        if ClerkUserProfile.objects.filter(clerk_user_id=user_id).exists():
            user_instance = ClerkUserProfile.objects.get(clerk_user_id=user_id)  # collecting the user instance from database.
            return user_id
            
        else:
            return 'ip'  # if user not found in our database , applying the default rate limit for unauthenticated users.
    else:
        return 'ip'  # default rate limit for unauthenticated users



def get_user_tier_based_rate_limit_for_chunking_of_files(group : str, request : HttpRequest):
    #since we are using the clerk for our ultimate authentication , first lets verfiy whether the user is authenticated or not.
    try:
        print("Entered into the rate limit function for chunked file upload")
        request_state = clerk_SDK.authenticate_request(
            request,
            AuthenticateRequestOptions(
                authorized_parties=["http://localhost:3000"]
            )
        )
    except Exception as e:
        print("You are in exception block of rate limit function")
        return '5/m'  # default rate limit for unauthenticated users.

    if request_state.is_signed_in:
        print("Entered into the rate limit function for chunked file upload (user is signed in )")
        request_payload = request_state.payload
        user_id = request_payload['sub']  # user ID
        #with the user id , tring to fetch the user from our database to check their tier.
        if ClerkUserProfile.objects.filter(clerk_user_id=user_id).exists():
            user_instance = ClerkUserProfile.objects.get(clerk_user_id=user_id)  # collecting the user instance from database.
            user_tier = user_instance.clerk_user_tier #collecting the user tier from the user instance.
            # applying the logic to return the rate limit based on the user tier.
            if user_tier == 'FREE':
                return '100/m'
            elif user_tier == 'PRO':
                return '250/m'
            elif user_tier == 'ADVANCED':
                return '500/m'
        else:
            return '5/m'  # if user not found in our database , applying the default rate limit for unauthenticated users.
    else:
        print("Entered into the rate limit function for chunked file upload (user is not signed in )")
        return '100/m'  # default rate limit for unauthenticated users