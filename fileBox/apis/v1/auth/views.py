import os

from dotenv import load_dotenv
from rest_framework.response import Response
from rest_framework.decorators import api_view

from clerk_backend_api import Clerk
from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions

from Backend.models import ClerkUserProfile , ClerkUserStorage

load_dotenv()

clerk_SDK = Clerk(bearer_auth=os.getenv("CLERK_API_KEY"))        #initializing the clerk sdk with the api key.

@api_view(['POST'])
def create_clerk_user(request):
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=["http://localhost:3000"]
        )
    )

    if request_state.is_signed_in:
        request_payload = request_state.payload
        user_id = request_payload['sub']  # user ID

        #get the user from clerk who is requesting the request.
        clerk_user = clerk_SDK.users.get(user_id=user_id)

        #gettiing the username and primary email address from clerk user object
        username = clerk_user.username
        profile_image = clerk_user.profile_image_url
        primary_email_address_id = clerk_user.primary_email_address_id  #getting the primary email address id from clerk user object.
        emails = clerk_user.email_addresses
        email = None

        #getting the correct email address using the primary email address id.
        for correct_email in emails:
            if correct_email.id == primary_email_address_id:
                email = correct_email.email_address
                break
        

        instance = ClerkUserProfile.objects.create(
            
            clerk_user_id = user_id,
            clerk_user_name = username,
            clerk_user_email = email,
            clerk_user_profile_img = profile_image,
        )

        ClerkUserStorage.objects.create(
            author = instance,
            clerk_user_storage_limit = 5,
            clerk_user_used_storage = 0,
            total_image_storage = 0,
            total_document_storage = 0,
            total_other_storage = 0
        )

        responce_data = {
            "status_code" : 5000,
            "message" : "Clerk User synced successfully",
            "data" : ""
        }
        return Response(responce_data)
    else:
        responce_data = {
            "status_code" : 5001,
            "message" : "User Can't able to sync. Authentication Failed",
            "data" : ""
        }
        return Response(responce_data)
    

@api_view(['POST'])
def update_clerk_user(request):
    #authenticating using the clerk sdk provided for python.
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=["http://localhost:3000"]
        )
    )
    print("passed the section 1")
    if request_state.is_signed_in:                   #checking whether the request is signed in or not.
        request_payload = request_state.payload      #getting the payload from the request state.
        user_id = request_payload['sub']             #getting the user id from the payload.
        print("passed the section 2")
        #get the user from clerk who is requesting the request.
        clerk_user = clerk_SDK.users.get(user_id=user_id)
        print("passed the section 3")
        #gettiing the username and primary email address from clerk user object
        username = clerk_user.username
        profile_image = clerk_user.profile_image_url
        primary_email_address_id = clerk_user.primary_email_address_id  #getting the primary email address id from clerk user object.
        emails = clerk_user.email_addresses
        email = None
        print("passed the section 4")
        #getting the correct email address using the primary email address id.
        for correct_email in emails:
            if correct_email.id == primary_email_address_id:
                email = correct_email.email_address
                break

        #Updating the user details in our database.
        user_Instance = ClerkUserProfile.objects.get(clerk_user_id = user_id)
        user_Instance.clerk_user_name = username
        user_Instance.clerk_user_email = email,
        user_Instance.clerk_user_profile_img = profile_image
        user_Instance.save()
        print("passed the section 5")
        responce_data = {
            "status_code" : 5000,
            "message" : "Clerk User updated successfully",
            "data" : ""
        }
        return Response(responce_data)

    else:
        print("passed the section 6")
        responce_data = {
            "status_code" : 5001,
            "message" : "User Can't able to sync. Authentication Failed",
            "data" : request_state
        }
        return Response(responce_data)


