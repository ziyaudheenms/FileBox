import json
import os

from dotenv import load_dotenv
from rest_framework.response import Response
from rest_framework.decorators import api_view

from clerk_backend_api import Clerk
from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions

from Backend.models import ClerkUserProfile , ClerkUserStorage, UserSecurityProfile
from .serializers import UserSecuritySessionSerializers

load_dotenv()

clerk_SDK = Clerk(bearer_auth=os.getenv("CLERK_API_KEY"))        #initializing the clerk sdk with the api key.
import json
import logging
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db import transaction
from clerk_backend_api import AuthenticateRequestOptions

logger = logging.getLogger(__name__)

@api_view(['POST'])
def create_clerk_user(request):
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=["http://localhost:3000"]
        )
    )

    if not request_state.is_signed_in:
        return Response({
            "status_code": 5001,
            "message": "User Can't able to sync. Authentication Failed",
            "data": ""
        }, status=401)

    request_payload = request_state.payload
    user_id = request_payload['sub']  # Clerk User ID

    # 1. Fetch user data from Clerk
    try:
        clerk_user = clerk_SDK.users.get(user_id=user_id)
    except Exception as e:
        logger.error(f"Failed to fetch Clerk user {user_id}: {e}")
        return Response({"status_code": 5002, "message": "Failed to verify Clerk user", "data": ""}, status=500)

    username = clerk_user.username
    profile_image = clerk_user.profile_image_url
    primary_email_address_id = clerk_user.primary_email_address_id
    emails = clerk_user.email_addresses
    email = None

    for correct_email in emails:
        if correct_email.id == primary_email_address_id:
            email = correct_email.email_address
            break

    # 2. Parse the incoming request body safely
    try:
        raw_payload = request.body.decode('utf-8')
        body_data = json.loads(raw_payload)
        # Depending on your axios request structure: 
        # If axios sent { payload: { salt: ..., publicKey: ... } }, use body_data.get('payload', {})
        # If axios sent the keys directly at the root, use body_data.
        crypto_payload = body_data.get('payload', body_data) 
    except Exception as e:
        logger.error(f"Invalid JSON payload: {e}")
        # Cleanup Clerk user immediately since crypto payload is invalid
        try:
            clerk_SDK.users.delete(user_id=user_id)
        except Exception:
            pass
        return Response({"status_code": 5003, "message": "Invalid crypto payload format", "data": ""}, status=400)

    # 3. Database operations inside an atomic transaction with rollback safety net
    try:
        with transaction.atomic():
            instance = ClerkUserProfile.objects.create(
                clerk_user_id=user_id,
                clerk_user_name=username,
                clerk_user_email=email,
                clerk_user_profile_img=profile_image,
            )

            ClerkUserStorage.objects.create(
                author=instance,
                clerk_user_storage_limit=1048576,  # 1 GB in KB
                clerk_user_used_storage=0,
                total_image_storage=0,
                total_document_storage=0,
                total_other_storage=0
            )

            UserSecurityProfile.objects.create(
                user=instance,
                key_encryption_key_salt=crypto_payload.get('salt'),
                user_public_key=crypto_payload.get('publicKey'),
                user_encrypted_private_key=crypto_payload.get('encryptedPrivateKey'),
                user_encrypted_private_key_nonce=crypto_payload.get('privateKeyNonce'),
                user_encrypted_master_key=crypto_payload.get('encryptedMasterKey'),
                user_encrypted_master_key_nonce=crypto_payload.get('masterkeyNonce')
            )

    except Exception as db_error:
        logger.error(f"Database creation failed for user {user_id}: {db_error}")

        # ROLLBACK SAFETY NET: Delete user from Clerk so they aren't left with an orphaned account
        try:
            clerk_SDK.users.delete(user_id=user_id)
            logger.info(f"Successfully rolled back orphaned Clerk user: {user_id}")
        except Exception as clerk_delete_error:
            logger.error(f"CRITICAL: Failed to delete orphaned Clerk user {user_id}: {clerk_delete_error}")

        return Response({
            "status_code": 5004,
            "message": "Database error while saving cryptographic records. Registration rolled back.",
            "data": ""
        }, status=500)

    return Response({
        "status_code": 5000,
        "message": "Clerk User synced successfully",
        "data": ""
    })


@api_view(['GET'])
def retrieve_crypto_sessions(request):
    """
        This function through we have to send the crypto sessions encrypted ones that which we have saved 
        in the DB to the respected users who are verified through the clerk SDK
    
    """
    request_state = clerk_SDK.authenticate_request(
            request,
            AuthenticateRequestOptions(
                authorized_parties=["http://localhost:3000"]
            )
        )
    
    if not request_state.is_signed_in:
        return Response({
            "status_code": 5001,
            "message": "User Can't able to sync. Authentication Failed",
            "data": ""
        }, status=401)

    request_payload = request_state.payload
    user_id = request_payload['sub']  # Clerk User ID

    user = ClerkUserProfile.objects.filter(clerk_user_id = user_id).first()
    if not user:
        return Response({
            "status_code" : 4001,
            "message" : "User Record Not Found",
            "data" : ""               
        })

    #Now we want to fetch the user security record and send it back to the client.

    user_security_instance = UserSecurityProfile.objects.filter(user = user).first()
    if not user_security_instance:
        return Response({
            "status_code" : 5002,
            "message" : "Opps !! We cant fing the user security crypto record",
            "data" : ""               
        })

    context = {
        "request" : request
    }

    serialized_security_sessions = UserSecuritySessionSerializers(instance = user_security_instance , context = context)

    return Response({
        "status_code" : 5000,
        "message" : "Stay Protected With Our Encryption",
        "data" : serialized_security_sessions.data               
    })
    




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
        user_Instance.clerk_user_email = email
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


