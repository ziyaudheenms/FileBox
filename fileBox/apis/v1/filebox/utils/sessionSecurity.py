import os
from functools import wraps
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.contrib.auth.hashers import check_password
from Backend.models import SecuritySession, FileFolderModel, ClerkUserProfile

from clerk_backend_api import Clerk
from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions

from fileBox.apis.v1.filebox.hashDependency import hash_ID

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
            
            file_folder_id = request.params.get('fileFolderID') 
            if isinstance(file_folder_id, str) and file_folder_id: 
                file_folder_id = hash_ID.decode_id(file_folder_id) #used to decode the hashed ID if the shared resource is been tried 
            
            file_folder_instance = FileFolderModel.objects.filter(pk=file_folder_id).first() 
            if not file_folder_instance: 
                responce_data = { 
                    'status_code' : 5001, 
                    'message' : 'Record instance not found', 
                    'data' : '' 
                } 
                return Response(responce_data)
            #bypassing the logic for author when its not critical 
            
            kwargs['user'] = user
            kwargs['file_folder'] = file_folder_instance

            if not file_folder_instance.is_critical and user == file_folder_instance.author: 
                return view_func(request, *args, **kwargs)   #calling our view function
            
            #checking if the password_protected has been implemented 
            if not file_folder_instance.is_password_protected: 
                return view_func(request, *args, **kwargs)  #calling our view function
            
            #checking the access pass_key send from the frontend with the security_pass_key we have in the db. 
            security_session_instance = SecuritySession.objects.filter(file_folder_instance=file_folder_instance , session_user=user).first() 
            if not security_session_instance: 
                responce_data = { 
                    'status_code' : 5003, 
                    'message' : 'session not found', 
                    'data' : '' 
                } 
                return Response(responce_data) 
        
            security_pass_key = security_session_instance.session_token  #pass key stored in the db (hashed one)
            token_from_frontend = request.headers.get('X-Security-Pass-Key') #pass key send from the frontend (raw one) 
            
            if not token_from_frontend or not security_pass_key or not check_password(token_from_frontend, security_pass_key) or security_session_instance.expiry_time < timezone.now():  #checking if the pass key is valid by checking if its there in the db and also checking if the token from the frontend matches with the decrypted token from the db and also checking if the token is expired or not by comparing the expiry time with the current time.
                responce_data = { 
                    'status_code' : 4005, 
                    'message' : 'Security pass key may have been expired', 
                    'data' : '' 
                } 
                return Response(responce_data) 
                       
        else: 
            responce_data = { 
                'status_code' : 4001, 
                'message' : 'User not authenticated', 
                'data' : '' 
            } 
            return Response(responce_data)
        
    return _wrapped_view