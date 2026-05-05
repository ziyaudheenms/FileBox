import os
from functools import wraps
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.contrib.auth.hashers import check_password
from Backend.models import ResourceSecurityPolicies, SecuritySession, FileFolderModel, ClerkUserProfile

from clerk_backend_api import Clerk
from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions

from ..hashDependency import hash_ID

clerk_SDK = Clerk(bearer_auth=os.getenv("CLERK_API_KEY"))  

def verify_session(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # 1. Clerk Authentication Check
        request_state = clerk_SDK.authenticate_request(
            request,
            AuthenticateRequestOptions(
                authorized_parties=['http://localhost:3000']
            )
        )
        if request_state.is_signed_in: 
            request_payload = request_state.payload 
            user_id = request_payload['sub'] 
            user = ClerkUserProfile.objects.filter(clerk_user_id = user_id).first() 

            if user is None: 
                responce_data = { 
                    "status_code" : 4001, 
                    "message" : "User Record Not Found", 
                    "data" : "" 
                } 
                
                return Response(responce_data) 
            kwargs['user'] = user
            
            raw_id = request.query_params.get('fileFolderID') or request.query_params.get('parentFolderID')

            if not raw_id:
                # If neither is present, it might be a root request or an error
                # You decide if you want to allow this or return an error
                return view_func(request, *args, **kwargs)


            file_folder_id = raw_id  # this setup is to include both the files and folders...


            ## checking for bypassing the actual ids and decoding the hashed ids if the shared resource is being tried to access.
            if file_folder_id:
                if file_folder_id.isdigit():
                    file_folder_id = int(file_folder_id)  # Convert to integer if it's a digit
                else:
                    file_folder_id = hash_ID.decode_id(file_folder_id) #used to decode the hashed ID if the shared resource is been tried 
            
            print("Decoded File/Folder ID:", file_folder_id)  # Debugging statement to check the decoded ID
            print("Raw File/Folder ID from query params:", raw_id)  # Debugging statement to check the raw ID from query params
            print("User ID:", user_id)  # Debugging statement to check the user ID from Clerk payload
            print("User from DB:", user.clerk_user_name)  # Debugging statement to check the user retrieved from the database
            
            security_policy = ResourceSecurityPolicies.objects.filter(file_folder_instance__pk=file_folder_id).first()

            if security_policy:           
                kwargs['file_folder'] = security_policy.file_folder_instance
            else:
                kwargs['file_folder'] = FileFolderModel.objects.filter(pk=file_folder_id).first()


            if not security_policy:
                return view_func(request, *args, **kwargs)  #if the security policy instance is not found for the file/folder instance then we will just call the view function without any security checks as there are no security policies implemented for that file/folder instance.

            if security_policy.is_locked: #if the author is set the resource locked , each time they access the resource have to provide the password
                temp_short_access_cokkie = request.COOKIES.get(f'short_time_access_{file_folder_id}')
                if temp_short_access_cokkie:
                    return view_func(request , *args, **kwargs)  #grand access to the resource
                else:
                    responce_data = {
                        'status_code' : 4005, 
                        'message' : 'Locked Resource , Enter The Password.', 
                        'data' : '' 
                    } 
                    return Response(responce_data)


            if not security_policy.is_critical and user == security_policy.file_folder_instance.author: 
                return view_func(request, *args, **kwargs)   #calling our view function
            
            #checking if the password_protected has been implemented 
            if not security_policy.is_password_protected: 
                return view_func(request, *args, **kwargs)  #calling our view function
            
            #checking the access pass_key send from the frontend with the security_pass_key we have in the db. 
            security_session_instance = SecuritySession.objects.filter(file_folder_instance=security_policy.file_folder_instance , session_user=user).first() 
            if not security_session_instance: 
                responce_data = { 
                    'status_code' : 5003, 
                    'message' : 'session not found', 
                    'data' : '' 
                } 
                return Response(responce_data) 

            if security_policy.is_locked: 
                responce_data = {
                    'status_code' : 4005, 
                    'message' : 'Locked Resource , Enter The Password.', 
                    'data' : '' 
                } 
                return Response(responce_data)


            security_pass_key = security_session_instance.session_token  #pass key stored in the db (hashed one)
            print(f'file_access_{file_folder_id}')
            token_from_frontend = request.COOKIES.get(f'file_access_{file_folder_id}') #pass key send from the frontend (raw one) 
            print(request.COOKIES)
            print("Token from frontend:", token_from_frontend)  # Debugging statement to check the token from the frontend
            if not token_from_frontend or not security_pass_key or not check_password(token_from_frontend, security_pass_key) or security_session_instance.expiry_time < timezone.now():  #checking if the pass key is valid by checking if its there in the db and also checking if the token from the frontend matches with the decrypted token from the db and also checking if the token is expired or not by comparing the expiry time with the current time.
                responce_data = { 
                    'status_code' : 4005, 
                    'message' : 'Security pass key may have been expired', 
                    'data' : '' 
                } 
                return Response(responce_data)
             
            return view_func(request, *args, **kwargs) #if all test cases are passed call the function   
        else: 
            responce_data = { 
                'status_code' : 4001, 
                'message' : 'User not authenticated', 
                'data' : '' 
            } 
            return Response(responce_data)
        
    return _wrapped_view