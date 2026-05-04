import os
from django.utils import timezone
from datetime import timedelta
import uuid
import base64
import shutil
from sqlite3 import Cursor
from sre_compile import isstring
from sys import version
from tkinter import NO, TRUE
from attr import has
from click import File
from django.contrib.auth.hashers import make_password, check_password
from django.db.models import F
from django.core.exceptions import ValidationError
from django.db.models import Q, Value
from django.db.models.functions import Replace
from django.db import transaction, models
# importing django cache system 
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django_redis.cache import RedisCache

#importing the dotenv packages and rest framework packages 
from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchHeadline
from django.db.models.functions import Coalesce
from dotenv import load_dotenv
from h11 import Request
from httpx import delete
from rest_framework.response import Response
from rest_framework.decorators import api_view

# pakckages for clerk integration
from clerk_backend_api import Clerk
from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions

#packages for imagekit integration
from imagekitio import ImageKit

#importing the queue tasks for Celery to work on with
from Backend.tasks import delete_image_from_imagekit, implement_copy_of_records, upload_image_to_imagekit

#importing the ratelimiting fuctions
from django_smart_ratelimit import rate_limit
from django_ratelimit.decorators import ratelimit

from Backend.models import ClerkUserStorage, FileFolderModel, ClerkUserProfile, FileFolderPermission, ResourceSecurityPolicies, SecuritySession, ShareLink # importing the models from the registered app
from Backend.ratelimit import get_user_tier_based_rate_limit , get_user_role_or_ip, get_user_tier_based_rate_limit_for_chunking_of_files
from .serializers import ChildFileFolderShareSerializer, FileFolderSerializer, FileFolderShareSerializer, SearchResultSerializer, SecurityPolicySerializer, ShareChildFileFolderShareSerializer, UserStorageSerializer, PermissionUserSerializer
from .pagination import FileFolderCursorBasedPagination  #custom pagination class for file/folder GET API responce
from ..hashDependency import hash_ID
from ..utils import permission , copyToolkit
from ..utils.sessionSecurity import verify_session #importing the session security decorator for verifiying the session
clerk_SDK = Clerk(bearer_auth=os.getenv("CLERK_API_KEY"))  


redis_cache: RedisCache = cache # type: ignore

@api_view(['POST'])
@ratelimit(key=lambda g, request: get_user_role_or_ip(g, request), rate=lambda g, request: get_user_tier_based_rate_limit(g, request) , block=True)  #used for getting the rate limiting based on the teir of the user
@rate_limit(key=lambda g, request: get_user_role_or_ip(g, request), rate='100/m', block=True, algorithm='token_bucket',algorithm_config={
        'bucket_size': 200,  # Allow bursts up to 200 requests
        'refill_rate': 2.0,  # Refill at 2 tokens per second
    })  # used for implementing token bucket algorithm for rate limiting
def uploadImage(request):
    # First Lets authenticate the request using clerk
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=['http://localhost:3000']
        )
    )
    if request_state.is_signed_in:
        request_payload = request_state.payload
        user_id = request_payload['sub']  # user ID

        folder_name_info = request.query_params.get("folderID") #if the image is stored inside any folder , we can get the ID of the folder
        file = request.data['image']

        sharable_UUID = request.query_params.get("sharableUUID")
        parent_hash = request.query_params.get("parentHash")



        file_bytes = file.read()
        file_base64 = base64.b64encode(file_bytes).decode('utf-8')
        filename = file.name
        filesize = file.size
        filename_with_extension = file.name
        root , extension = os.path.splitext(filename_with_extension)

        user = ClerkUserProfile.objects.get(clerk_user_id = user_id)

        folder = None #initializing the parent folder.
        delete_cache_key = None
        root_folder=None #used to track the shared folder<main>

        if folder_name_info is not None:  #calculations for if the owner uploads directly
            if FileFolderModel.objects.filter(pk = folder_name_info).exists():
                folder = FileFolderModel.objects.get(pk = folder_name_info)
                delete_cache_key = f'*file_folder_list_{user.clerk_user_id}_*'
            else:
                folder = None 

        elif sharable_UUID is not None:
            share_instance_folder = ShareLink.objects.select_related('file_folder_instance').filter(shareable_id=sharable_UUID).first()
            print("collected the share root folder")
            
            if not share_instance_folder:
                return Response({"status_code": 5001, "message": "Shared instance not found" , "data" : ""})

            root_folder = share_instance_folder.file_folder_instance
            permission_granded = None
            

            if root_folder.author == user:
                permission_granded = ('OWNER' , )
                print('the user requesting to upload is a owner')
            else:
                permission_instance = FileFolderPermission.objects.filter(fileFolder_Instance_id=root_folder, user_id=user).first()
                print('collecting the request status of the user')

                if permission_instance:
                    ids = (root_folder.path.split("/") if root_folder.path else []) + [str(root_folder.pk)]
                    permission_granded = permission.grand_permission_for_shared_instance(ids, user, permission_instance)
                    print(f'permission granted for the user is {permission_granded}')
                else:
                    return Response({"status_code": 5001, "message": "Permission Record not found"})

            if permission_granded[0] in ['EDIT', 'ADMIN', 'OWNER']:
                if parent_hash:
                    print(1)

                    child_id = hash_ID.decode_id(parent_hash)
                    child_folder = FileFolderModel.objects.filter(pk=child_id).first()
                    print(1)
                    
                    path_list = child_folder.path.split('/') if child_folder and child_folder.path else []
                    if child_folder and str(root_folder.pk) in path_list:
                        folder = child_folder
                        delete_cache_key = f'*sharable_{root_folder.pk}_{child_id}_*'
                    else:
                        return Response({"status_code": 5001, "message": "Invalid Parent ID"})
                else:
                    folder = root_folder
                    delete_cache_key = f'*sharable_{root_folder.pk}_*'
            else:
                return Response({"status_code": 5001, "message": "Access for upload denied", "data" : ""})

        
        

        ## Calculations so that to determine the path , handled the edge case of if the parent's path  is none 
        path_to_be_appended = None
        if folder is not None:
            if folder.path is not None:
                path_to_be_appended = f'{folder.path}/{folder.pk}'
            else:
                path_to_be_appended = f'{folder.pk}'

        #creating the dummy record for reference in the frontend()
        file_instance = FileFolderModel.objects.create(
            author = user,
            name = root,
            size = filesize,
            is_root = True if folder == None else False,
            path = path_to_be_appended,
            type_of_file_folder = 'image',
            parentFolder = folder,
            file_url = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTEpYntNMtkoBOau-IFwoq7wUlivz4VfNir9g&s",
            file_extension = extension,
            celery_task_ID = 1
        )
        #task is queued to work at offload , so that to avoid the smooth fuctioning of api and workflow of the system.
        print(file_instance.pk)


        if file_instance.is_root: #root records can be only made by the origignal owners......
            print("deleting thr image.........(root)")
            redis_cache.delete_pattern(f'*file_folder_list_{file_instance.author.clerk_user_id}_*', version=2)
        else:
            print("deleting thr image.........")
            if delete_cache_key:
                redis_cache.delete_pattern( delete_cache_key, version=2)  #for deleting the shared instance 
            
            redis_cache.delete_pattern(f'*file_folder_list_{folder.author.clerk_user_id if folder else None}_{file_instance.parentFolder.pk if file_instance.parentFolder != None else None}*', version=2)  #clearing the cache of the owner(who shared...)


        queue_worker = upload_image_to_imagekit.delay(filename , file_base64 , file_instance.pk ,delete_cache_key , root_folder.author if root_folder else None)

        file_instance.celery_task_ID = queue_worker.id
        file_instance.save()

        responce_data = {
            "status_code" : 5000,
            "message" : "Image Added to Queue Successfully, Upload Started",
            "data" : hash_ID.encode_id(file_instance.pk) if sharable_UUID else file_instance.pk,            
        }

        return Response(responce_data)
    else:
        responce_data = {
            "status_code" : 4001,
            "message" : "User not authenticated",
            "data" : ""
        }

    return Response(responce_data)


@api_view(['POST'])
@ratelimit(key=lambda g, request: get_user_role_or_ip(g, request), rate=lambda g, request: get_user_tier_based_rate_limit_for_chunking_of_files(g, request) , block=True)  #used for getting the rate limiting based on the teir of the user
@rate_limit(key=lambda g, request: get_user_role_or_ip(g, request), rate='100/m', block=True, algorithm='token_bucket',algorithm_config={
        'bucket_size': 200,  # Allow bursts up to 200 requests
        'refill_rate': 2.0,  # Refill at 2 tokens per second
    })  # used for implementing token bucket algorithm for rate limiting
def ChunkImage(request):
    #collecting all the important details.
    chunk = request.data["chunk"]
    chunk_index = request.data["chunkIndex"]
    total_chunk = request.data["totalChunks"]
    chunk_file_ID = request.data["fileId"]
    chunk_file_name = request.data["fileName"]

    # Create a temporary directory for the file if it doesn't exist
    temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_chunks', chunk_file_ID)
    os.makedirs(temp_dir, exist_ok=True)

    # Store the chunk with chunk_index as the file name
    chunk_path = os.path.join(temp_dir, str(chunk_index))
    with open(chunk_path, 'wb') as f:
        f.write(chunk.read())

    responce_data = {
        "status_code" : 5000,
        "message" : "Started Uploading the chunks",
        "data" : ""
    }

    return Response(responce_data)


@api_view(["POST"])
@ratelimit(key=lambda g, request: get_user_role_or_ip(g, request), rate=lambda g, request: get_user_tier_based_rate_limit(g, request) , block=True)  #used for getting the rate limiting based on the teir of the user
@rate_limit(key=lambda g, request: get_user_role_or_ip(g, request), rate='100/m', block=True, algorithm='token_bucket',algorithm_config={
        'bucket_size': 200,  # Allow bursts up to 200 requests
        'refill_rate': 2.0,  # Refill at 2 tokens per second
    })  # used for implementing token bucket algorithm for rate limiting
def JoinChunks(request):
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=['http://localhost:3000']
        )
    )
    if request_state.is_signed_in:
        request_payload = request_state.payload
        user_id = request_payload['sub']

        chunk_file_ID = request.data["fileId"]
        full_file_name = request.data["fileName"]
        file_size = request.data["fileSize"]
        file_extenstion = request.data["fileExtenstion"]
        
        # Separate name and extension
        file_name = os.path.splitext(full_file_name)[0]

        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_chunks', chunk_file_ID)
        if not os.path.exists(temp_dir):
            responce_data = {
                "status_code": 4004,
                "message": "Chunks folder not found",
                "data": ""
            }
            return Response(responce_data)

        # Get all chunk files, sort by filename (which is the chunk index)
        chunk_files = sorted(
            [f for f in os.listdir(temp_dir) if f.isdigit()],
            key=lambda x: int(x)
        )

        output_dir = os.path.join(settings.MEDIA_ROOT, 'joined_files')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{chunk_file_ID}_joined")

        with open(output_path, 'wb') as outfile:
            for chunk_file in chunk_files:
                chunk_path = os.path.join(temp_dir, chunk_file)
                with open(chunk_path, 'rb') as infile:
                    outfile.write(infile.read())

        # Read the merged file into bytes
        with open(output_path, 'rb') as merged_file:
            bytes_data = merged_file.read()

        user = ClerkUserProfile.objects.get(clerk_user_id = user_id)
        folder_name_info = request.query_params.get("folderID") #if the image is stored inside any folder , we can get the ID of the folder
        folder = None #initializing the parent folder.
        if folder_name_info is not None:
            if FileFolderModel.objects.filter(pk = folder_name_info).exists():
                folder = FileFolderModel.objects.get(pk = folder_name_info)
            else:
                folder = None

        path_to_be_appended = None
        if folder is not None:
            if folder.path is not None:
                path_to_be_appended = f'{folder.path}/{folder.pk}'
            else:
                path_to_be_appended = f'{folder.pk}'

        #creating the dummy record for reference in the frontend()
        file_instance = FileFolderModel.objects.create(
            author = user,
            name = file_name,
            size = file_size,
            is_root = True if folder == None else False,
            path = path_to_be_appended,
            parentFolder = folder,
            file_url = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTEpYntNMtkoBOau-IFwoq7wUlivz4VfNir9g&s",
            file_extension = file_extenstion,
            celery_task_ID = 1
        )
        #task is queued to work at offload , so that to avoid the smooth fuctioning of api and workflow of the system.
        print(file_instance.pk)
        file_base64 = base64.b64encode(bytes_data).decode('utf-8')
        queue_worker = upload_image_to_imagekit.delay(file_name , file_base64 , file_instance.pk)
        file_instance.celery_task_ID = queue_worker.id
        file_instance.save()

        if file_instance.is_root:
            print("deleting thr image.........(root)")
            redis_cache.delete_pattern(f'*file_folder_list_{user.clerk_user_id}_*', version=2)
        else:
            print("deleting thr image.........")
            redis_cache.delete_pattern(f'*file_folder_list_{user.clerk_user_id}_{file_instance.parentFolder.pk if file_instance.parentFolder != None else None}*', version=2)

        responce_data = {
            "status_code": 5000,
            "message": "Image Queued Successfully",
            "data": file_instance.pk
        }

        os.remove(output_path)  # Delete the joined file created by joining chunks
        shutil.rmtree(temp_dir, ignore_errors=True) # Delete the temporary directory after joining chunks
        return Response(responce_data)
    else:
        responce_data = {
            "status_code" : 4001,
            "message" : "User not authenticated",
            "data" : ""
        }

    return Response(responce_data)


@api_view(['POST'])
@ratelimit(key=lambda g, request: get_user_role_or_ip(g, request), rate=lambda g, request: get_user_tier_based_rate_limit(g, request) , block=True)  #used for getting the rate limiting based on the teir of the user
@rate_limit(key=lambda g, request: get_user_role_or_ip(g, request), rate='100/m', block=True, algorithm='token_bucket',algorithm_config={
        'bucket_size': 200,  # Allow bursts up to 200 requests
        'refill_rate': 2.0,  # Refill at 2 tokens per second
    })  # used for implementing token bucket algorithm for rate limiting
def createFolder(request):
    # First Lets authenticate the request using clerk
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=["http://localhost:3000"]
        )
    )

    if request_state.is_signed_in:
        request_payload = request_state.payload
        user_id = request_payload['sub']

        user = ClerkUserProfile.objects.get(clerk_user_id = user_id)  #getting the authenticated author who is creating the folder  
        folder_name_info = request.query_params.get("folderID") # parent folder ID
        folder_name = request.data["name"]

        sharable_UUID = request.query_params.get("sharableUUID")
        parent_hash = request.query_params.get("parentHash")

        print(folder_name_info)

        folder = None #initializing the parent folder.
        delete_cache_key = None

        if folder_name_info is not None:
            if FileFolderModel.objects.filter(pk = folder_name_info).exists():
                folder = FileFolderModel.objects.get(pk = folder_name_info)
            else:
                folder = None
        elif sharable_UUID is not None:
            share_instance_folder = ShareLink.objects.select_related('file_folder_instance').filter(shareable_id=sharable_UUID).first()
            print("collected the share root folder")
            
            if not share_instance_folder:
                return Response({"status_code": 5001, "message": "Shared instance not found" , "data" : ""})

            root_folder = share_instance_folder.file_folder_instance
            permission_granded = None
            

            if root_folder.author == user:
                permission_granded = ('OWNER' , )
                print('the user requesting to upload is a owner')
            else:
                permission_instance = FileFolderPermission.objects.filter(fileFolder_Instance_id=root_folder, user_id=user).first()
                print('collecting the request status of the user')

                if permission_instance:
                    ids = (root_folder.path.split("/") if root_folder.path else []) + [str(root_folder.pk)]
                    permission_granded = permission.grand_permission_for_shared_instance(ids, user, permission_instance)
                    print(f'permission granted for the user is {permission_granded}')
                else:
                    return Response({"status_code": 5001, "message": "Permission Record not found"})

            if permission_granded[0] in ['EDIT', 'ADMIN', 'OWNER']:
                if parent_hash:
                    child_id = hash_ID.decode_id(parent_hash)
                    child_folder = FileFolderModel.objects.filter(pk=child_id).first() 
                    path_list = child_folder.path.split('/') if child_folder and child_folder.path else []
                    if child_folder and str(root_folder.pk) in path_list:
                        folder = child_folder
                        delete_cache_key = f'*sharable_{root_folder.pk}_{child_id}_*'
                    else:
                        return Response({"status_code": 5001, "message": "Invalid Parent ID"})
                else:
                    folder = root_folder
                    delete_cache_key = f'*sharable_{root_folder.pk}_*'
            else:
                return Response({"status_code": 5001, "message": "Access for upload denied", "data" : ""})

        print(folder)

        path_to_be_appended = None
        if folder is not None:
            if folder.path is not None:
                path_to_be_appended = f'{folder.path}/{folder.pk}'
            else:
                path_to_be_appended = f'{folder.pk}'
    
        folder_instance = FileFolderModel.objects.create(
            author = user,
            name = folder_name,
            size = 0,
            isfolder = True,
            is_root = True if folder == None else False,
            path = path_to_be_appended,
            parentFolder = folder,
            upload_status = "UPLOADED"
        )
        
        responce_data = {
                "status_code" : 5000,
                "message" : "folder Created Successfully",
                "data" : hash_ID.encode_id(folder_instance.pk) if sharable_UUID else folder_instance.pk,
            }

        
        redis_cache: RedisCache = cache # type: ignore
        if folder_instance.is_root:
            redis_cache.delete_pattern(f'*file_folder_list_{folder_instance.author.clerk_user_id}_*', version=2)
        else:
            if delete_cache_key:
                redis_cache.delete_pattern( delete_cache_key, version=2)
            redis_cache.delete_pattern(f'*file_folder_list_{folder.author.clerk_user_id}_{folder_instance.parentFolder.pk}*', version=2)

        return Response(responce_data)
    else:
        responce_data = {
            "status_code" : 4001, 
            "message" : "User not authenticated",
            "data" : ""
        }
        return Response(responce_data)

@api_view(["GET"])
@ratelimit(key=lambda g, request: get_user_role_or_ip(g, request), rate=lambda g, request: get_user_tier_based_rate_limit(g, request) , block=True)  #used for getting the rate limiting based on the teir of the user
@rate_limit(key=lambda g, request: get_user_role_or_ip(g, request), rate='100/m', block=True, algorithm='token_bucket',algorithm_config={
        'bucket_size': 200,  # Allow bursts up to 200 requests
        'refill_rate': 2.0,  # Refill at 2 tokens per second
})  # used for implementing token bucket algorithm for rate limiting
def isTrash(request):
    # First Lets authenticate the request using clerk
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=["http://localhost:3000"]
        )
    )

    if request_state.is_signed_in:
        # Initializing the imagekit sdk
        request_payload = request_state.payload
        user_id = request_payload['sub']

        user = ClerkUserProfile.objects.get(clerk_user_id = user_id)  #getting the authenticated author who is creating the folder  
        folder_file_id = int(request.query_params.get("folderFileID"))  #the instance whoose Trash Status has to be updated
        cursor_key = request.query_params.get("cursor") #Cursor key (for incoperating the pagination with cache.)

        print(cursor_key , 'this is the cursor key...........')

        if FileFolderModel.objects.filter(pk=folder_file_id , author = user).exists():
            instance = FileFolderModel.objects.get(pk=folder_file_id, author = user)
            parent_folder_id = None  if instance.parentFolder == None else instance.parentFolder.pk   #if we are inside a parent folder , if the child is been Trash updated , we need to remove the cache inside that parent Folder not the entire root, for that we need the ID of particular parent.
            print(parent_folder_id , "parent folder ID for deleting the cache.")
            print("entered into the trash update function")
            instance.is_trash = False if instance.is_trash else True  # Updating the trash status based on its current state
            instance.save()

            responce_data = {
                "status_code" : 5000,
                "message" : "Fodler/File Updated Successfully",
                "data" : ""
            }   
            redis_cache: RedisCache = cache # type: ignore
            redis_cache.delete_pattern(f'*trashed_{user.clerk_user_id}_*', version=2)

            
            if parent_folder_id:  #clearing the parent folder not the root 
                redis_cache.delete_pattern(f'*file_folder_list_{user.clerk_user_id}_{parent_folder_id}_*', version=2)
                return Response(responce_data)
            else: #clearing the entire root , since the trash update fileFolder might be a root level Record..
                redis_cache.delete_pattern(f'*file_folder_list_{user.clerk_user_id}_*', version=2)
                return Response(responce_data)

        else:
            responce_data = {
                "status_code" : 5002,
                "message" : "Fodler/File Not Found",
                "data" : ""
            }
            return Response(responce_data)
    else:
        responce_data = {
            "status_code" : 4001,
            "message" : "User not authenticated",
            "data" : ""
        }
        return Response(responce_data)


@api_view(["GET"])
@ratelimit(key=lambda g, request: get_user_role_or_ip(g, request), rate=lambda g, request: get_user_tier_based_rate_limit(g, request) , block=True)  #used for getting the rate limiting based on the teir of the user
@rate_limit(key=lambda g, request: get_user_role_or_ip(g, request), rate='100/m', block=True, algorithm='token_bucket',algorithm_config={
        'bucket_size': 200,  # Allow bursts up to 200 requests
        'refill_rate': 2.0,  # Refill at 2 tokens per second
    })  # used for implementing token bucket algorithm for rate limiting
def isFavorite(request):
    # First Lets authenticate the request using clerk
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=["http://localhost:3000"]
        )
    )

    if request_state.is_signed_in:
        request_payload = request_state.payload
        user_id = request_payload['sub']

        user = ClerkUserProfile.objects.get(clerk_user_id = user_id)  #getting the authenticated author who is creating the folder  
        folder_file_id = int(request.query_params.get("folderFileID"))

        if FileFolderModel.objects.filter(pk=folder_file_id , author = user).exists():
            instance = FileFolderModel.objects.get(pk=folder_file_id, author = user)
            instance.is_favorite = False if instance.is_favorite else True  # Updating the favorite status based on its current state
            instance.save()

            responce_data = {
                "status_code" : 5000,
                "message" : "Fodler/File Updated Successfully",
                "data" : ""
            }


            redis_cache: RedisCache = cache # type: ignore  
            redis_cache.delete_pattern(f'*favorites_{user.clerk_user_id}_*', version=2)
            
            if instance.parentFolder is not None:  #clearing the parent folder not the root     
                redis_cache.delete_pattern(f'*file_folder_list_{user.clerk_user_id}_{instance.parentFolder.pk}_*', version=2)
                return Response(responce_data)
            else: #clearing the entire root , since the trash update fileFolder might be a root level Record..
                redis_cache.delete_pattern(f'*file_folder_list_{user.clerk_user_id}_*', version=2)
                return Response(responce_data)

        else:
            responce_data = {
                "status_code" : 5002,
                "message" : "Fodler/File Not Found",
                "data" : ""
            }
            return Response(responce_data)
    else:
        responce_data = {
            "status_code" : 4001,
            "message" : "User not authenticated",
            "data" : ""
        }
        return Response(responce_data)
    

@api_view(['GET'])
@rate_limit(key='ip', rate='1/m')
def testFunction(request):
    responce_data = {
        "status_code" : 5000,
        "message" : "Hello world",
        "data" : ""
    }

    return Response(responce_data)


@api_view(['GET'])
@verify_session
def getAllFileFolders(request,user=None , file_folder=None):
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=['http://localhost:3000']
        )
    )
    if request_state.is_signed_in:
        request_payload = request_state.payload
        user_id = request_payload['sub']
        user = ClerkUserProfile.objects.get(clerk_user_id = user_id)
        if not user:
            responce_data = {
                "status_code" : 4001,
                "message" : "User Record Not Found",
                "data" : ""
            }
            return Response(responce_data)
        
        parent_folder_id = request.query_params.get("parentFolderID") #if we want to get the files/folders inside any specific folder , we can get the id of that folder through this param
        pagination_cursor = request.query_params.get("cursor")
        category_type = request.query_params.get("category")   #allowed_types = [IMAGE, DOCUMENT, VIDEO, OTHERS]
        if category_type and not category_type in ["image", "document", "video", "others"]:
            responce_data = {
                "status_code" : 5002,
                "message" : "Invalid category type",
                "data" : ""
            }
            return Response(responce_data)
        
        cache_key = f'{category_type}_file_folder_list_{user.clerk_user_id}_{parent_folder_id}_{pagination_cursor}' if category_type else f'file_folder_list_{user.clerk_user_id}_{parent_folder_id}_{pagination_cursor}'  # setting the Cache Key for the specific user and parent folder ID and pagination cursor to look up in the cache.
        print('Generated Cache Key', cache_key)

        #looking up in cache for the required data.
        if cache.has_key(cache_key , version=2):
            print('Fetching from cache version 2', cache_key)
            return Response(cache.get(cache_key , version=2))
        
        parentFolder = FileFolderModel.objects.filter(pk = parent_folder_id).first() #for building the breadcrumbs
        if parent_folder_id is not None:
            all_files_folders_instance = FileFolderModel.objects.filter(is_trash = False , parentFolder = parent_folder_id ).order_by('-updated_at')
        else:
            all_files_folders_instance = FileFolderModel.objects.filter(is_trash = False, author = user, type_of_file_folder=category_type).order_by('-updated_at') if category_type else FileFolderModel.objects.filter(is_trash = False , is_root = True , author = user).order_by('-updated_at')

        if not all_files_folders_instance.exists():
            responce_data = {
                "status_code" : 5002,
                "message" : "No Files/Folders Found",
                "data" : ""
            }
            return Response(responce_data)
        
        
        ids =  (parentFolder.path.split('/') if parentFolder.path else []) if parentFolder else []
        ids.append(parent_folder_id) 
        folderNames = FileFolderModel.objects.filter(pk__in =ids).values_list('name', flat=True)
        pathname =  '/'.join(folderNames)

        print(pathname , ids , "-> used for breadcrumbs")

        paginated_files_folders = FileFolderCursorBasedPagination()
        paginated_instance = paginated_files_folders.paginate_queryset(all_files_folders_instance , request)

        context = {
            "request" : request
        }

        if paginated_instance is not None:
            serialized_files_and_folders = FileFolderSerializer(paginated_instance, many = True , context = context)
            result = paginated_files_folders.get_paginated_response(serialized_files_and_folders.data , breadcrumb_details= {
                    "names" : pathname,
                    "ids" : ("/".join(ids) if ids else '') if parentFolder else '' 
                }).data
            cache.set(cache_key, result ,version=2)  #setting the required data in cache against the cache key for future lookups.
            print("setting the cached value")
            return paginated_files_folders.get_paginated_response(serialized_files_and_folders.data , breadcrumb_details= {
                    "names" : pathname,
                    "ids" : ("/".join(ids) if ids else '') if parentFolder else '' 
                })
        
        serialized_files_and_folders = FileFolderSerializer(all_files_folders_instance, many = True , context = context)
        print(serialized_files_and_folders.data , cache_key , "OUTSIDE THE PAGINATION CLASS.....")
        responce_data = {
                "status_code" : 5000,
                "message" : "Folder Created Successfully",
                "data" : serialized_files_and_folders.data,
                "breadcrumbs" : {
                    "names" : pathname,
                    "ids" : ("/".join(ids) if ids else '') if parentFolder else '' 
                }
        }
        
        cache.set(cache_key, responce_data)
        return Response(responce_data)
    else: 
        print('token has expired or user not authenticated' , request_state , request)
        responce_data = {
            "status_code" : 4001,
            "message" : "User not authenticated",
            "data" : ""
        }

        return Response(responce_data)
    


@api_view(['GET'])
def getTrashFileFolders(request):
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=['http://localhost:3000']
        )
    )
    if request_state.is_signed_in:
        request_payload = request_state.payload
        user_id = request_payload['sub']

        user = ClerkUserProfile.objects.get(clerk_user_id = user_id)
        if not user:
            responce_data = {
                "status_code" : 4001,
                "message" : "User Record Not Found",
                "data" : ""
            }
            return Response(responce_data)
        
        pagination_cursor = request.query_params.get("cursor")
        cache_key = f'trashed_{user.clerk_user_id}_{pagination_cursor}' # setting the Cache Key for the specific user and parent folder ID and pagination cursor to look up in the cache.
        print(cache_key)
        if cache.has_key(cache_key , version=2):
            print('Fetching from cache version 2(trash Page)', cache_key)
            return Response(cache.get(cache_key , version=2))

        all_files_folders_instance = FileFolderModel.objects.filter(is_trash = True  , author = user).order_by('-updated_at')

        if not all_files_folders_instance.exists():
            responce_data = {
                "status_code" : 5002,
                "message" : "No Files/Folders Found",
                "data" : ""
            }
            return Response(responce_data)
        
        paginated_files_folders = FileFolderCursorBasedPagination()
        paginated_instance = paginated_files_folders.paginate_queryset(all_files_folders_instance , request)

        context = {
            "request" : request
        }

        if paginated_instance is not None:
            serialized_files_and_folders = FileFolderSerializer(paginated_instance, many = True , context = context)
            result = paginated_files_folders.get_paginated_response(serialized_files_and_folders.data).data
            cache.set(cache_key, result ,version=2)  #setting the required data in cache against the cache key for future lookups.
            print("setting the cached value(trash)")
            return paginated_files_folders.get_paginated_response(serialized_files_and_folders.data)
        
        serialized_files_and_folders = FileFolderSerializer(all_files_folders_instance, many = True , context = context)
        responce_data = {
                "status_code" : 5000,
                "message" : "Folder Created Successfully",
                "data" : serialized_files_and_folders.data
        }
        
        return Response(responce_data)
    else: 
        responce_data = {
            "status_code" : 4001,
            "message" : "User not authenticated",
            "data" : ""
        }

        return Response(responce_data)


@api_view(['GET'])
def getFavoriteFileFolders(request):
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=['http://localhost:3000']
        )
    )
    if request_state.is_signed_in:
        request_payload = request_state.payload
        user_id = request_payload['sub']

        user = ClerkUserProfile.objects.get(clerk_user_id = user_id)
        if not user:
            responce_data = {
                "status_code" : 4001,
                "message" : "User Record Not Found",
                "data" : ""
            }
            return Response(responce_data)
        
        pagination_cursor = request.query_params.get("cursor")
        cache_key = f'favorites_{user.clerk_user_id}_{pagination_cursor}'
        if cache.has_key(cache_key , version=2):
            print("fetching the responce from Favorite Cache....")
            return Response(cache.get(cache_key , version=2))


        all_files_folders_instance = FileFolderModel.objects.filter(is_trash = False  , author = user , is_favorite = True).order_by('-updated_at')

        if not all_files_folders_instance.exists():
            responce_data = {
                "status_code" : 5002,
                "message" : "No Files/Folders Found",
                "data" : ""
            }
            return Response(responce_data)
        
        paginated_files_folders = FileFolderCursorBasedPagination()
        paginated_instance = paginated_files_folders.paginate_queryset(all_files_folders_instance , request)

        context = {
            "request" : request
        }

        if paginated_instance is not None:
            serialized_files_and_folders = FileFolderSerializer(paginated_instance, many = True , context = context)
            result = paginated_files_folders.get_paginated_response(serialized_files_and_folders.data).data
            print('setting the favorite section')
            cache.set(cache_key , result , version=2)
            return paginated_files_folders.get_paginated_response(serialized_files_and_folders.data)
        
        serialized_files_and_folders = FileFolderSerializer(all_files_folders_instance, many = True , context = context)
        responce_data = {
                "status_code" : 5000,
                "message" : "Folder Updated Successfully",
                "data" : serialized_files_and_folders.data
        }
        
        return Response(responce_data)
    else: 
        responce_data = {
            "status_code" : 4001,
            "message" : "User not authenticated",
            "data" : ""
        }

        return Response(responce_data)





@api_view(['GET'])
@verify_session  #custom decorator to verify the session and also to pass the user and file_folder_instance.
def getSingleResource(request , user=None , file_folder=None):  # user and the file_folder_instance are passed by custom decorator
    #API enpoint to get single image details based on the image ID passed through the query params
    context = {
        "request" : request
    }
    serialized_resource = FileFolderSerializer(file_folder , context = context)

    responce_data = {
        "status_code" : 5000,
        "message" : "Resource Fetched Successfully",
        "data" : serialized_resource.data
    }

    return Response(responce_data)
    
@api_view(['GET'])
def getStorageDetails(request):
    #API endpoint to get the storage details of the user
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
        if not user:
            responce_data = {
                "status_code" : 4001,
                "message" : "User Record Not Found",
                "data" : ""
            }
            return Response(responce_data)
        
        storage_cache_key = f'storage_stat_of_{user_id}'
        print(storage_cache_key)
        if cache.has_key(storage_cache_key , version=1):
            print('Fetching from cache version 1(storage stats)')
            return Response(cache.get(storage_cache_key , version=1))
        

        storage_instance = ClerkUserStorage.objects.get(author = user)
        if not storage_instance:
            responce_data = {
                "status_code" : 5002,
                "message" : "Storage Record Not Found",
                "data" : ""
            }
            return Response(responce_data)
        context = {
                "request" : request
            }
        serialized_storage_data = UserStorageSerializer(storage_instance, context = context)
        print("setting new cache/.....")
        cache.set(storage_cache_key, serialized_storage_data.data, version=1)

        responce_data = {
            "status_code" : 5000,
            "message" : "Storage Details Fetched Successfully",
            "data" : serialized_storage_data.data
        }

        return Response(responce_data)
    else:
        responce_data = {
            "status_code" : 4001,
            "message" : "User not authenticated",
            "data" : ""
        }
        return Response(responce_data)


@api_view(['POST'])
def get_the_user_for_permission(request):
    #This Endpoint is used to return the users based on their email addresses so that to fix them with the permissions for accessing our filefolder models.
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=['http://localhost:3000']
        )
    )
    if request_state.is_signed_in:
        request_payload = request_state.payload
        user_id = request_payload['sub']
        user = ClerkUserProfile.objects.get(clerk_user_id = user_id)
        if not user:
            responce_data = {
                "status_code" : 4001,
                "message" : "User Record Not Found",
                "data" : ""
            }
            return Response(responce_data)

        user_permission_email_begining_with = request.data.get('userToFind')
        if ClerkUserProfile.objects.filter(clerk_user_email__startswith = user_permission_email_begining_with).exists():
            instance = ClerkUserProfile.objects.filter(clerk_user_email__icontains = user_permission_email_begining_with)
            context = {
                "request" : request
            }
            serialized_data = PermissionUserSerializer(instance, many=True , context=context)
            responce_data = {
                "status_code" : 5000,
                "message" : f"Users with email that starts with {user_permission_email_begining_with}",
                "data" : serialized_data.data
            }
            return Response(responce_data)
        else:
             responce_data = {
                "status_code" : 5002,
                "message" : "Opps ! No user found with the given email.",
                "data" : ""
             }
             return Response(responce_data)


    else:
        responce_data = {
            "status_code" : 4001,
            "message" : "User not authenticated",
            "data" : ""
        }
        return Response(responce_data)


@api_view(['POST'])
def assign_permission_to_user(request):
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=['http://localhost:3000']
        )
    )
    if request_state.is_signed_in:
        request_payload = request_state.payload
        user_id = request_payload['sub']
        user = ClerkUserProfile.objects.get(clerk_user_id = user_id)
        if not user:
            responce_data = {
                "status_code" : 4001,
                "message" : "User Record Not Found",
                "data" : ""
            }
            return Response(responce_data)
        
        file_folder_instance = None
        #updating the function so that admin and owner both can assign the permissions to other users, but the owner will have the permission to assign the admin role to other users 
        fileFolderID = request.query_params.get("fileFolderID")
        sharable_UUID = request.query_params.get("sharableUUID")
        hashed_record_id = request.query_params.get("childSharableHash")
        if fileFolderID:
            file_folder_instance = FileFolderModel.objects.select_related('author').filter(pk=fileFolderID).first()  # By using this we can reduce the number of queries to fetch the author details while fetching the permissions for the filefolder instance (check + fetch in one step) if not found , it will give none.
            if not file_folder_instance:
                responce_data = {
                    "status_code" : 5001,
                    "message" : "Folder Not found",
                    "data" : ""
                }
                return Response(responce_data)

        # permission_folder = FileFolderPermission.objects.filter(fileFolder_Instance_id = file_instance , user_id = user).first() #checking if the user have any permission assigned for the filefolder instance or not (check + fetch in one step) if not found , it will give none.
        
        elif sharable_UUID:
            share_record = ShareLink.objects.select_related('file_folder_instance').filter(shareable_id=sharable_UUID).first()
            if not share_record:
                return Response({"status_code": 5001, "message": "You are not assigned to share this." , "data" : ""})
            root_share_folder = share_record.file_folder_instance
            permission_granded = None

            if root_share_folder.author == user:
                permission_granded = ('OWNER' , )
                print('the user requesting to upload is a owner')
            else:
                permission_instance = FileFolderPermission.objects.filter(fileFolder_Instance_id=root_share_folder, user_id=user).first()
                print('collecting the request status of the user')
                if permission_instance:
                    ids = (root_share_folder.path.split("/") if root_share_folder.path else []) + [str(root_share_folder.pk)]
                    permission_granded = permission.grand_permission_for_shared_instance(ids, user, permission_instance)
                    print(f'permission granted for the user is {permission_granded}')
                else:
                    return Response({"status_code": 5001, "message": "Permission Record not found"})
                
            if permission_granded[0] in ['ADMIN', 'OWNER']:
                if hashed_record_id:
                    child_id = hash_ID.decode_id(hashed_record_id)
                    child_folder = FileFolderModel.objects.filter(pk=child_id).first()     
                    path_list = child_folder.path.split('/') if child_folder and child_folder.path else []

                    if child_folder and str(root_share_folder.pk) in path_list:
                        file_folder_instance = child_folder
                        # delete_cache_key = f'*sharable_{root_folder.pk}_{child_id}_*'
                    else:
                        return Response({"status_code": 5001, "message": "Invalid Record ID"})  
                else:
                    file_folder_instance = root_share_folder
                    # delete_cache_key = f'*sharable_{root_folder.pk}_*'
            else:
                return Response({"status_code": 5001, "message": "Access for controlling share denieed", "data" : ""})
        
        if file_folder_instance:
            is_owner = file_folder_instance.author.clerk_user_id == user_id
            # is_admin = permission_folder.permission_type == 'ADMIN' if permission_folder else False

            data_to_assign_permission = request.data['usersToGrandPermission']  #Array of objects that contains the emai and permission to assign permission.
            data_to_remove_permission = request.data['usersToRemovePermission']  #Array of objects that contains the emai and permission to remove them.
            try:
                with transaction.atomic():
                    
                    if len(data_to_assign_permission) > 0: #checking if both the arrays are empty or not , if they are empty then there is no need to perform any operation on database and we can directly return the responce.
                        # collecting the email addresses
                        emails_to_assign_with_permission = [item['email'].strip() for item in data_to_assign_permission]  #List of email addresses to whom the permission is going to be assigned.
                        #mapping the users {email : user instance}
                        users = {
                            u.clerk_user_email : u for u in ClerkUserProfile.objects.filter(clerk_user_email__in = emails_to_assign_with_permission) #fetching the user instances for the email addresses to whom the permission is going to be assigned in one query and creating a dictionary with email as key and user instance as value for the future use.
                        }
                        permissions_to_be_allocated = [] #List to hold the permission instances to be created for bulk creation.
                        for item in data_to_assign_permission:
                            email = item['email'].strip()
                            permission_to_allocate = item['permission'].strip()

                            if permission_to_allocate not in ['VIEW' , 'EDIT' , 'ADMIN']:
                                responce_data = {
                                    "status_code" : 5002,
                                    "message" : "The Given User Role Doesnt Exists !",
                                    "data" : ""
                                }
                                return Response(responce_data)
                            
                            if permission_to_allocate == 'ADMIN' and not is_owner:
                                responce_data = {
                                    "status_code" : 5002,
                                    "message" : "Only Owner Can Assign Admin Role To Other Users !",
                                    "data" : ""
                                }
                                return Response(responce_data)
                            
                            #checking if the user exists to whom we want to assign permission
                            user_to_assign_permission_clerk_instance = users.get(email)
                            if not user_to_assign_permission_clerk_instance:
                                responce_data = {
                                    "status_code" : 5002,
                                    "message" : "User Not Found To Be Assigned With Permission!",
                                    "data" : ""
                                }
                                return Response(responce_data)

                            #we dont need to create a permission class for the author , there for verfifying that using a if clause.
                            if email != user.clerk_user_email:
                                permissions_to_be_allocated.append(
                                    FileFolderPermission(
                                        fileFolder_Instance_id = file_folder_instance,
                                        user_id = user_to_assign_permission_clerk_instance,
                                        permission_type = permission_to_allocate
                                    )
                                )
                    
                        if permissions_to_be_allocated:
                            FileFolderPermission.objects.bulk_create(
                                permissions_to_be_allocated,
                                update_conflicts=True,  # This is an important part of this bulk create function , what it does is if the record already exists it just updates it with update field.
                                unique_fields=['fileFolder_Instance_id', 'user_id'],  # This is also an important part of this bulk create function , it tells that which fields to look for to check the existing record for updating the record if already exists while creating the new one.
                                update_fields=['permission_type']  # This is also an important part of this bulk create function , it tells that which field to update if the record already exists while creating the new one.
                            )
                        
                    email_to_remove_permission_list = [item['email'].strip() for item in data_to_remove_permission]  #List of email addresses to whom the permission is going to be removed.
                    if email_to_remove_permission_list:
                        permission_record_with_user = FileFolderPermission.objects.filter(fileFolder_Instance_id = file_instance , user_id__clerk_user_email__in = email_to_remove_permission_list)#Joint Query is performed , user_id__ is used to access the fields of the related model (ClerkUserProfile) while filtering the FileFolderPermission model based on the email of the user to whom the permission is going to be removed.
                        if permission_record_with_user.count() != len(email_to_remove_permission_list):  #checking if the number of permission records found with the given email addresses is same as the number of email addresses to whom the permission is going to be removed or not , if not then it means that some of the email addresses are invalid which are not present in our clerk user profile or they are not having any permission assigned for that filefolder instance.
                            responce_data = {
                                "status_code" : 5002,
                                "message" : "Some of the email addresses provided for removing the permissions are invalid or they are not having any permission assigned for this file/folder instance!",
                                "data" : ""
                            }
                            return Response(responce_data)
                        permission_record_with_user.delete()  #deleting the permission record to remove the permissions from the user.
                        
                                                    
                responce_data = {
                    "status_code" : 5000,
                    "message" : "Successfully Updated the permissions..",
                    "data" : ""
                }
           
                redis_cache.delete_pattern(f'*users_with_permission_{file_folder_instance.pk}*', version=2)

                return Response(responce_data)
            except Exception as e:
                responce_data = {
                    "status_code" : 5002,
                    "message" : "Some error Occured...",
                    "error" : e
                }
                return Response(responce_data)
            
        else:
            responce_data = {
                "status_code" : 5002,
                "message" : "OPPS ! No object Found.",
                "data" : ""
            }
            return Response(responce_data)
    else:
        responce_data = {
            "status_code" : 4001,
            "message" : "User not authenticated",
            "data" : ""
        }
        return Response(responce_data)



@api_view(['GET'])
def get_User_With_Permission(request):
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=['http://localhost:3000']
        )
    )
    if request_state.is_signed_in:
        request_payload = request_state.payload
        user_id = request_payload['sub']
        user = ClerkUserProfile.objects.get(clerk_user_id = user_id)
        if not user:
            responce_data = {
                "status_code" : 4001,
                "message" : "User Record Not Found",
                "data" : ""
            }
            return Response(responce_data)
        
        fileFolderID = request.query_params.get("fileFolderID")  #always number , its send by the actual owner 
        sharable_UUID = request.query_params.get("sharableUUID")
        hashed_record_id = request.query_params.get("childSharableHash")
        file_folder_instance = None  #used to track the Particular Record

        if fileFolderID:
            file_folder_instance = FileFolderModel.objects.select_related('author').filter(pk=fileFolderID).first()  # By using this we can reduce the number of queries to fetch the author details while fetching the permissions for the filefolder instance (check + fetch in one step) if not found , it will give none.
            if not file_folder_instance:
                responce_data = {
                    "status_code" : 5001,
                    "message" : "Opps ! FileFolder Record not found",
                    "data" : ""
                }
                return Response(responce_data)
            
        elif sharable_UUID:
            share_record = ShareLink.objects.select_related('file_folder_instance').filter(shareable_id=sharable_UUID).first()
            if not share_record:
                return Response({"status_code": 5001, "message": "You are not assigned to share this." , "data" : ""})
            root_share_folder = share_record.file_folder_instance
            permission_granded = None

            if root_share_folder.author == user:
                permission_granded = ('OWNER' , )
                print('the user requesting to upload is a owner')
            else:
                permission_instance = FileFolderPermission.objects.filter(fileFolder_Instance_id=root_share_folder, user_id=user).first()
                print('collecting the request status of the user')
                if permission_instance:
                    ids = (root_share_folder.path.split("/") if root_share_folder.path else []) + [str(root_share_folder.pk)]
                    permission_granded = permission.grand_permission_for_shared_instance(ids, user, permission_instance)
                    print(f'permission granted for the user is {permission_granded}')
                else:
                    return Response({"status_code": 5001, "message": "Permission Record not found"})
                
            if permission_granded[0] in ['ADMIN', 'OWNER']:
                if hashed_record_id:
                    child_id = hash_ID.decode_id(hashed_record_id)
                    child_folder = FileFolderModel.objects.filter(pk=child_id).first()     
                    path_list = child_folder.path.split('/') if child_folder and child_folder.path else []

                    if child_folder and str(root_share_folder.pk) in path_list:
                        file_folder_instance = child_folder
                        # delete_cache_key = f'*sharable_{root_folder.pk}_{child_id}_*'
                    else:
                        return Response({"status_code": 5001, "message": "Invalid Record ID"})  
                else:
                    file_folder_instance = root_share_folder
                    # delete_cache_key = f'*sharable_{root_folder.pk}_*'
            else:
                return Response({"status_code": 5001, "message": "Access for controlling share denieed", "data" : ""})

   
        user_with_access_cache_key = f"users_with_permission_{file_folder_instance.pk if file_folder_instance else None}"
        if cache.has_key(user_with_access_cache_key , version=2):
            print("collecting from permission cache....")
            return Response(cache.get(user_with_access_cache_key , version=2))

        try:
            permitted_users_instance = FileFolderPermission.objects.filter(fileFolder_Instance_id = file_folder_instance)
            serialized_data = [  #populating it with the author details with permission as owner
                {
                "id" : file_folder_instance.author.pk if file_folder_instance else None,
                "username" : file_folder_instance.author.clerk_user_name if file_folder_instance else None,
                "email" : file_folder_instance.author.clerk_user_email if file_folder_instance else None,
                "profile" : file_folder_instance.author.clerk_user_profile_img if file_folder_instance else None,
                "permission" : "OWNER"
                }
            ]
            for permitted_user in permitted_users_instance:
                res = {
                    "id" : permitted_user.pk,
                    "username" : permitted_user.user_id.clerk_user_name,
                    "email" : permitted_user.user_id.clerk_user_email,
                    "profile" : permitted_user.user_id.clerk_user_profile_img,
                    "permission" : permitted_user.permission_type
                }
                serialized_data.append(res)

            responce_data = {
                "status_code" : 5000,
                "message" : "Successfully Fetched The Data",
                "data" : serialized_data
            }
            cache.set(user_with_access_cache_key, responce_data, version=2)
            return Response(responce_data)
        except FileFolderPermission.DoesNotExist:
            responce_data = {
                "status_code" : 5001,
                "message" : "Permission Record doesnt found",
                "data" : ""
            }
            return Response(responce_data)
        except Exception as e:
            responce_data = {
                "status_code" : 5001,
                "message" : "Some error occured in the process...",
                "error" : e
            }
            return Response(responce_data)
    else:
        responce_data = {
            "status_code" : 4001,
            "message" : "User not authenticated",
            "data" : ""
        }
        return Response(responce_data)
   


@api_view(['POST'])
def generate_share_link(request):
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=['http://localhost:3000']
        )
    )
    if request_state.is_signed_in:
        request_payload = request_state.payload
        user_id = request_payload['sub']
        user = ClerkUserProfile.objects.get(clerk_user_id = user_id)
        if not user:
            responce_data = {
                "status_code" : 4001,
                "message" : "User Record Not Found",
                "data" : ""
            }
            return Response(responce_data)

        file_folder_id = request.query_params.get("fileFolderID")
        file_folder_type = request.query_params.get("type") #used to generate the url with 'image' or 'documents' or 'others' or 'folder'
        if not file_folder_id:
            responce_data = {
                "status_code" : 5002,
                "message" : "Record not Found",
                "data" : ""
            }
            return Response(responce_data)

        file_folder_instance = FileFolderModel.objects.select_related('author').filter(pk = file_folder_id).first()

        if file_folder_instance is None:
            responce_data = {
                "status_code" : 5002,
                "message" : "Record not Found",
                "data" : ""
            }
            return Response(responce_data)
        
        if file_folder_instance.author != user:
            responce_data = {
                "status_code" : 4001,
                "message" : "Forbidden , You have no acess",
                "data" : ""
            }
            return Response(responce_data)

        access_type = request.data.get('access_type') # this is for cumpolsary feature

        #extra contol features given to the pro and advanced premium users.
        if user.clerk_user_tier in ['PRO' ,'ADVANCED']:
            password = request.data.get('password')
            max_count = request.data.get('max_count')
            expires_at = request.data.get('expires_at')

        if not access_type in ['PUBLIC' , 'PRIVATE']:
            responce_data = {
                "status_code" : 5002,
                "message" : "Access Option is not Found",
                "data" : ""
            }
            return Response(responce_data)

        if user.clerk_user_tier in ['PRO' ,'ADVANCED']:
            # premium users can adjust or change there password or expiry time or  max_count
            try:

                with transaction.atomic():
                    sharable_instance , created = ShareLink.objects.get_or_create(
                        file_folder_instance = file_folder_instance,
                        view_type = access_type,
                        owner = user,
                        defaults = {
                            'file_folder_instance' : file_folder_instance,
                            'view_type' : access_type,
                            'data_type' : 'FOLDER' if file_folder_instance.isfolder else 'FILE',
                            'owner' : user,
                            'password_hash' :  make_password(password) if password else None,
                            "max_count" : max_count,
                            "expires_at" : expires_at
                        }
                    )
            except Exception as e:
                 responce_data = {
                    "status_code" : 5002,
                    "message" : "some error occured with generating the URL",
                    "data" : ""
                 }
                 return Response(responce_data)
        
        
            
        elif user.clerk_user_tier in ['FREE']:
            try:
                with transaction.atomic():
                    sharable_instance , created = ShareLink.objects.get_or_create(
                        file_folder_instance = file_folder_instance,
                        view_type = access_type,
                        owner = user,
                        defaults = {
                            'file_folder_instance' : file_folder_instance,
                            'view_type' : access_type,
                            'data_type' : 'FOLDER' if file_folder_instance.isfolder else 'FILE',
                            'owner' : user,
                        }
                    )
            except Exception as e:
                 responce_data = {
                    "status_code" : 5002,
                    "message" : "some error occured with generating the URL",
                    "data" : ""
                 }
                 return Response(responce_data)
        
        sharable_link = f'sharable/{file_folder_type}/{sharable_instance.shareable_id}'
        responce_data = {
            "status_code" : 5000,
            "message" : "Successfully Generated The URL",
            "data" : {
                "sharable_link" : sharable_link,
            }
        }

        return Response(responce_data)
    else:
        responce_data = {
            "status_code" : 4001,
            "message" : "User not authenticated",
            "data" : ""
        }
        return Response(responce_data)


@api_view(['POST'])
def access_shared_file_folder(request):
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=['http://localhost:3000']
        )
    )
    if request_state.is_signed_in:
        request_payload = request_state.payload
        user_id = request_payload['sub']
        user = ClerkUserProfile.objects.get(clerk_user_id = user_id)
        if not user:
            responce_data = {
                "status_code" : 4001,
                "message" : "User Record Not Found",
                "data" : ""
            }
            return Response(responce_data)
        
        sharable_uuid = request.query_params.get("sharableUUID") #getting the ID from the params of the url.

        try:
            share_link_instance = ShareLink.objects.select_related('file_folder_instance').get(shareable_id = sharable_uuid) #collecting the instance based on the ID given in the URL.Select_related is used to reduce the number of queries to the database by fetching the related file_folder_instance in the same query as the ShareLink instance.  
        except ShareLink.DoesNotExist:
            responce_data = {
                "status_code" : 5002,
                "message" : "FileFolder Instance Not Found.",
                "data" : ""
            }
            return Response(responce_data)  
        except Exception as e:
             responce_data = {
                "status_code" : 5002,
                "message" : "FileFolder Instance Not Found.",
                "data" : ""
            }
             return Response(responce_data) 
        
        #trackers used to track the access control
        has_access = False
        permission_data = None
        is_folder = True if share_link_instance.file_folder_instance.isfolder else False  #if its folder we have to implement folder listing logic................
        is_owner = True if share_link_instance.file_folder_instance.author == user else False
        #for implementing the breadcrumbs with security......
        sharable_path_names = None 
        sharable_hash_code = None
        #Skipping all the checks and conditions for the OWNER......
        if not is_owner:
            if not share_link_instance.is_active:
                responce_data = {
                    "status_code" : 5001,
                    "message" : "FileFolder Instance Not Found.",
                    "data" : ""
                }
                return Response(responce_data)
            
            if share_link_instance.is_expired:
                responce_data = {
                    "status_code" : 5004,
                    "message" : "Link is_expired, it cant be used....",
                    "data" : ""
                }
                return Response(responce_data)
            
            if share_link_instance.count_limited:
                responce_data = {
                    "status_code" : 5006,
                    "message" : "The No Of Times The Link Should Use Crossed The Limit.",
                    "data" : ""
                }
                return Response(responce_data)


        if share_link_instance.view_type == "PUBLIC" or is_owner:
            has_access = True  
            permission_data = {
                "permission_type" : "OWNER" if is_owner else "PUBLIC",
                "permission_granded_at" : None if not is_owner else share_link_instance.file_folder_instance.uploaded_at,
            }  
        elif share_link_instance.view_type == "PRIVATE":
            file_permission_instance = FileFolderPermission.objects.filter(fileFolder_Instance_id = share_link_instance.file_folder_instance , user_id = user).first()  #this approch reduces the hit to the server by checking and collecting the first record just in one DB hit -> Returns the value else None will be returned.
            if file_permission_instance:
                # Adding the extra permisson details also with the fileFolder data to the protected user.....
                has_access = True

                ids = share_link_instance.file_folder_instance.path.split("/") if share_link_instance.file_folder_instance.path else []
                ids.append(str(share_link_instance.file_folder_instance.pk))
                permissions = FileFolderPermission.objects.filter(fileFolder_Instance_id__in=ids).values_list('permission_type', flat=True)
                print(ids)
                #used for creating the path for the shared fileFolders  (BUILDING SECURE BREADCRUM PATHS FOR SHARING FUNCTIONALITY)
                first_id = FileFolderPermission.objects.filter(fileFolder_Instance_id__in=ids).order_by('fileFolder_Instance_id__path').values_list('fileFolder_Instance_id', flat=True).first()      # orderby is used so that to sort the records such that smallest path somes first eg a, a/b , a/b/c ect and we can easily get the original first one [BECAUSE .FILTER DOESNT GUARENTEES A ORDERD LISITING WHICH MEANS IT CAN GIVE AS a/b/c/d AS THE FIRST ONE ]
                start_index = ids.index(str(first_id)) if str(first_id) in ids else 0
                ids = ids[start_index:]
                print(first_id , ids , start_index)

                # Prepare Lookups
                name_map = dict(FileFolderModel.objects.filter(pk__in=ids).values_list('id', 'name'))
                hash_map = dict(ShareLink.objects.filter(file_folder_instance_id__in=ids).values_list('file_folder_instance_id', 'shareable_id'))

                # Convert keys to strings for matching
                name_map = {str(k): v for k, v in name_map.items()}
                hash_map = {str(k): str(v) for k, v in hash_map.items()}

                # Generate Ordered Strings
                sharable_path_names = '/'.join([name_map.get(str(i), "") for i in ids])
                sharable_hash_code = '/'.join([hash_map[str(i)] for i in ids if str(i) in hash_map])


                permission_mapping = {'VIEW': 1, 'EDIT': 2, 'ADMIN': 3}
                highest_permission = max([permission_mapping.get(p, 0) for p in permissions], default=0)
                
                permission_data = {
                    "permission_type" : list(permission_mapping.keys())[list(permission_mapping.values()).index(highest_permission)] if highest_permission > 0 else file_permission_instance.permission_type,
                    "permission_granded_at" : file_permission_instance.permission_granted_at,
                }

            elif share_link_instance.password_hash:
                password = request.data.get("password") #collecting the password from user.
                if not check_password(password , share_link_instance.password_hash):
                    responce_data = {
                        "status_code" : 5008,
                        "message" : "Wrong Password , Try Again Later!",
                        "data" : ""
                    }
                    return Response(responce_data)
                has_access=True  
            

        #is the user have no access , we return them Forbidden message......
        if not has_access:    
            responce_data = {
                "status_code" : 4002,
                "message" : "Forbidden ! You Have No Access.",
                "data" : ""
            }
            return Response(responce_data)
        
        if not is_owner: #skipping the access_count functionality for owner.......
            ShareLink.objects.filter(pk=share_link_instance.pk).update(
                access_count=F('access_count') + 1
            )
            share_link_instance.refresh_from_db() #refreshing it to get the new corrected values.....
        context = {
            "request" : request
        }

        if not is_folder:
            # This Section is used to return the files
            serialized_data = FileFolderShareSerializer(share_link_instance.file_folder_instance , context=context)
            data = serialized_data.data #getting the first elemt (we have only first...)
            
            if permission_data:
                data['permission_data'] = permission_data
            
            responce_data = {
                "status_code" : 5000,
                "message" : "Your Access Granted Successfully",
                "data" : data,
                "bread_crumbs" : {
                    "sharable_hash_codes" : sharable_hash_code,
                    "sharable_path_names" : sharable_path_names
                }
            }
            return Response(responce_data)
        
        else:
            # setting up the permission and breadcrumb details ....................   
            meta_data = {
                "permission_details" : permission_data, 
            }

            responce_data = {
                "status_code" : 5000,
                "message" : "Your Access Granted Successfully",
                "data" : meta_data
            }
            return Response(responce_data)
            
    else:
        responce_data = {
            "status_code" : 4001,
            "message" : "User not authenticated",
            "data" : ""
        }
        return Response(responce_data)


@api_view(['GET'])
def access_child_of_shared_folder(request):
    # This function is used to access the child of the shared folder when the user click on the folder in the shared folder listing page and it will return the listing of that folder with the permission data of the user for that folder and also with the breadcrumb details for that folder to show in the frontend while accessing the shared folders.
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=['http://localhost:3000']
        )
    )
    if request_state.is_signed_in:
        request_payload = request_state.payload
        user_id = request_payload['sub']
        user = ClerkUserProfile.objects.get(clerk_user_id = user_id)
        if not user:
            responce_data = {
                "status_code" : 4001,
                "message" : "User Record Not Found",
                "data" : ""
            }
            return Response(responce_data)

        sharable_UUID = request.query_params.get("sharableUUID") #getting the ID from the params of the url.
        #fetching the shareable instance based on the sharable UUID given in the URL and also fetching the related file_folder_instance in the same query to reduce the number of queries to the database.
        sharable_instance = ShareLink.objects.select_related('file_folder_instance' , 'owner').filter(shareable_id = sharable_UUID).first() 
        if sharable_instance is None:
            responce_data = {
                "status_code" : 5001,
                "message" : "FileFolder Instance Not Found.",
                "data" : ""
            }
            return Response(responce_data)
        
        parent_id = request.query_params.get("parentID") # this is the parent ID of the folder which we want to access in the shared folder listing page when we click on the folder to access it and see its content with the permission details and breadcrumb details for that folder.


        if parent_id:
            id_of_parent = hash_ID.decode_id(parent_id) if parent_id else None  #decoding the hashed ID to get the original ID of the parent folder to filter the child instances based on that parent folder ID.
            if id_of_parent is None:
                responce_data = {
                    "status_code" : 5001,
                    "message" : "Parent Folder Not Found.",
                    "data" : ""
                }
                return Response(responce_data)
        else:
            id_of_parent = sharable_instance.file_folder_instance.pk 
        
        
        parent_folder = FileFolderModel.objects.filter(pk = id_of_parent).first() #fetching the parent folder instance based on the decoded ID of the parent folder to check if the parent folder exists or not and also to check if the parent folder is in the path of the shared folder or not.
        if parent_folder is None:
            responce_data = {
                "status_code" : 5001,
                "message" : "Parent Folder Not Found.",
                "data" : ""
            }
            return Response(responce_data)
        
        #Performing the Test of does the parent folder tried to access the child actually beongs undeer the Shared Instance
        parent_path = parent_folder.path.split("/") if parent_folder.path else []  #getting the path of the parent folder to check if the parent folder is in the path of the shared folder or not.
        parent_path.append(str(parent_folder.pk)) #appending the parent folder ID to the path to make the complete path of the parent folder to check if the shared folder instance is in the path of the parent folder or not.
        Shared_Instance_is_ancestor_of_the_parent_folder = str(sharable_instance.file_folder_instance.pk) in parent_path  #checking if the shared folder instance is in the path of the parent folder or not to make sure that the user is trying to access the child of the shared folder or not.
        if not Shared_Instance_is_ancestor_of_the_parent_folder:
            responce_data = {
                "status_code" : 4002,
                "message" : "Forbidden ! You Are Trying To Access The Folder Which Is Not Under The Shared Folder.",
                "data" : ""
            }
            return Response(responce_data)


        parent_path = parent_path[parent_path.index(str(sharable_instance.file_folder_instance.pk)) : ]    
        queryset = FileFolderModel.objects.filter(pk__in=parent_path).values('id', 'name')
        name_map = {str(item['id']): item['name'] for item in queryset}

        ordered_breadcrumbs = []

        for folder_id in parent_path:
            if folder_id in name_map:
                ordered_breadcrumbs.append({
                    "name": name_map[folder_id],
                    "hashed_id": hash_ID.encode_id(int(folder_id)) if int(folder_id) != sharable_instance.file_folder_instance.pk else None
                })

        pagination_cursor = request.query_params.get("cursor")
        # redis_cache.delete_pattern(f'sharable_{sharable_instance.file_folder_instance.pk}_*', version=2)
        cache_key = f'sharable_{sharable_instance.file_folder_instance.pk}_{id_of_parent}_{pagination_cursor}' # setting the Cache Key for the specific user and parent folder ID and pagination cursor to look up in the cache.
        print('Generated Cache Key for sharable instance....', cache_key)

        #looking up in cache for the required data.
        if cache.has_key(cache_key , version=2):
            print('Fetching from cache version 2', cache_key)
            return Response(cache.get(cache_key , version=2))

        is_folder = parent_folder.isfolder  #Used to render FOLDERS or SPECIFIC FILE

        if is_folder: 
            all_child_instances = FileFolderModel.objects.filter(is_trash = False , parentFolder = parent_folder ).select_related('author').order_by('-updated_at')
            
            if not all_child_instances.exists():
                responce_data = {
                    "status_code" : 5002,
                    "message" : "No Files/Folders Found",
                    "data" : "",
                    "breadcrumb_details" : ordered_breadcrumbs
                }
                return Response(responce_data)
            
            paginated_files_folders = FileFolderCursorBasedPagination()
            paginated_instance = paginated_files_folders.paginate_queryset(all_child_instances , request)

            context = {
                "request" : request,
            }

            if paginated_instance is not None:
                serialized_files_and_folders = ChildFileFolderShareSerializer(paginated_instance, many = True , context = context)
                result = paginated_files_folders.get_paginated_response(serialized_files_and_folders.data , breadcrumb_details=ordered_breadcrumbs).data
                cache.set(cache_key, result ,version=2)  #setting the required data in cache against the cache key for future lookups.
                print("setting the cached value for shared folder listing....", cache_key)
                return paginated_files_folders.get_paginated_response(serialized_files_and_folders.data , breadcrumb_details=ordered_breadcrumbs)
            
            serialized_files_and_folders = ChildFileFolderShareSerializer(all_child_instances, many = True , context = context)
            print(serialized_files_and_folders.data , cache_key , "OUTSIDE THE PAGINATION CLASS.....")
            responce_data = {
                    "status_code" : 5000,
                    "message" : "Folder Created Successfully",
                    "data" : serialized_files_and_folders.data,
                    "breadcrumb_details" : ordered_breadcrumbs
            }
            
            cache.set(cache_key, responce_data)
            return Response(responce_data)
        else: #Processing the child file inside the shared Instance....................
            context = {
                'request' : request
            }
            serialized_file = ChildFileFolderShareSerializer(parent_folder , context = context).data
            responce_data = {
                "status_code" : 5000,
                "message" : "Image Fetched Successfully",
                "data" : serialized_file,
                "breadcrumb_details" : ordered_breadcrumbs
            }

            cache.set(cache_key, responce_data ,version=2)
            return Response(responce_data)
    
    else:
        responce_data = {
            "status_code" : 4001,
            "message" : "User not authenticated",
            "data" : ""
        }
        return Response(responce_data)

@api_view(['POST'])
def update_file_meta_data(request):
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
        if not user:
            responce_data = {
                "status_code" : 4001,
                "message" : "User Record Not Found",
                "data" : ""
            }
            return Response(responce_data)
        
        file_id = request.query_params.get("fileID")
        sharable_UUID = request.query_params.get("sharableUUID")
        file_hash = request.query_params.get("fileHash")

        file_Instance = None
        delete_cache_key = None

        if file_id:
            file_Instance = FileFolderModel.objects.filter(pk = file_id , author = user).first()
            if not file_Instance:
                responce_data = {
                    "status_code" : 5001,
                    "message" : "file not found",
                    "data" : ""
                }
                return Response(responce_data)
            
        elif sharable_UUID is not None:
            share_instance_folder = ShareLink.objects.select_related('file_folder_instance').filter(shareable_id=sharable_UUID).first()
            print("collected the share root folder")
            
            if not share_instance_folder:
                return Response({"status_code": 5001, "message": "Shared instance not found" , "data" : ""})

            root_folder = share_instance_folder.file_folder_instance
            permission_granded = None
            

            if root_folder.author == user:
                permission_granded = ('OWNER' , )
                print('the user requesting to upload is a owner')
            else:
                permission_instance = FileFolderPermission.objects.filter(fileFolder_Instance_id=root_folder, user_id=user).first()
                print('collecting the request status of the user')

                if permission_instance:
                    ids = (root_folder.path.split("/") if root_folder.path else []) + [str(root_folder.pk)]
                    permission_granded = permission.grand_permission_for_shared_instance(ids, user, permission_instance)
                    print(f'permission granted for the user is {permission_granded}')
                else:
                    return Response({"status_code": 5001, "message": "Permission Record not found"})

            if permission_granded[0] in ['EDIT', 'ADMIN', 'OWNER']:
                if file_hash:
                    child_id = hash_ID.decode_id(file_hash)
                    child_folder = FileFolderModel.objects.filter(pk=child_id).first()
                    
                    path_list = child_folder.path.split('/') if child_folder and child_folder.path else []
                    if child_folder and str(root_folder.pk) in path_list:
                        file_Instance = child_folder
                        delete_cache_key = f'*sharable_{root_folder.pk}_{child_folder.parentFolder.pk}_*'   #we need to clear the cache of the parent folder where this respective folder is present.

                    else:
                        return Response({"status_code": 5001, "message": "Invalid Parent ID"})
                else:
                    file_Instance = root_folder
                    delete_cache_key = f'*sharable_{root_folder.pk}_*'
            else:
                return Response({"status_code": 5001, "message": "Access for upload denied", "data" : ""})

        if file_Instance:
            description = request.data.get("description", None)
            name = request.data.get("name", None)

            if description:
                file_Instance.description = description 
            if name:
                file_name , extension = os.path.splitext(name)
                file_Instance.name = f"{file_name}"

                if file_Instance.is_root: #root records can be only made by the origignal owners......
                    print("deleting thr image.........(root)")
                    redis_cache.delete_pattern(f'*file_folder_list_{file_Instance.author.clerk_user_id}_*', version=2)
                else:
                    print("deleting thr image.........")
                    if delete_cache_key:
                        redis_cache.delete_pattern( delete_cache_key, version=2)  #for deleting the shared instance 
                    redis_cache.delete_pattern(f'*file_folder_list_{file_Instance.author.clerk_user_id}_{file_Instance.parentFolder.pk}*', version=2)  #clearing the cache of the owner(who shared...)
                        
            file_Instance.save()
            responce_data = {
                    "status_code" : 5000,
                    "message" : "successfully added the description",
                    "data" : ""
            }
            return Response(responce_data)
        else:
            responce_data = {
                    "status_code" : 5001,
                    "message" : "file Record not found",
                    "data" : ""
            }
            return Response(responce_data)


    else:
        responce_data = {
            "status_code" : 4001,
            "message" : "User not authenticated",
            "data" : ""
        }
        return Response(responce_data)


@api_view(['DELETE'])
def delete_filefolderRecord(request):
    """
        Only Authors of the respected file folders and owners of the parent folders can only perform the delete action.    
    """
    request_state = clerk_SDK.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=['http://localhost:3000']
        )
    )
    if request_state.is_signed_in:
        request_payload = request_state.payload
        user_id = request_payload['sub']
        user = ClerkUserProfile.objects.get(clerk_user_id = user_id)
        if not user:
            responce_data = {
                "status_code" : 4001,
                "message" : "User Record Not Found",
                "data" : ""
            }
            return Response(responce_data)
        file_folder_id = request.query_params.get("fileFolderID")
        sharable_UUID = request.query_params.get("sharableUUID")
        file_hash = request.query_params.get("fileFolderHash")

        print(file_folder_id , sharable_UUID , file_hash)

        file_folder_instance = None
        can_delete = False #variable which is used to track whther can delete 
        cache_delete_key = None
        cache_storage_key = None
        root_share_folder = None #used to track the shared folder

        if file_folder_id:
            file_folder_instance = FileFolderModel.objects.filter(pk = file_folder_id).first()
            if not file_folder_instance:
                responce_data = {
                    "status_code" : 5001,
                    "message" : "file not found",
                    "data" : ""
                }
                return Response(responce_data)
            
            if file_folder_instance.author == user :
                can_delete = True 
                cache_storage_key = f'storage_stat_of_{file_folder_instance.author.clerk_user_id}',
            else:
                can_delete = False

        elif sharable_UUID is not None:
            share_instance_folder = ShareLink.objects.select_related('file_folder_instance').filter(shareable_id=sharable_UUID).first()
            print("collected the share root folder")
            
            if not share_instance_folder:
                return Response({"status_code": 5001, "message": "Shared instance not found" , "data" : ""})
            
            cache_storage_key = f'storage_stat_of_{share_instance_folder.file_folder_instance.author.clerk_user_id}',
            root_share_folder = share_instance_folder.file_folder_instance
            if file_hash:
                file_ID = hash_ID.decode_id(file_hash)
                file_folder_instance = FileFolderModel.objects.filter(pk = file_ID).first()
                path_list = file_folder_instance.path.split('/') if file_folder_instance and file_folder_instance.path else []
                if file_folder_instance and str(share_instance_folder.file_folder_instance.pk) in path_list:
                    if file_folder_instance.author == user or root_share_folder.author == user:
                        can_delete = True
                        cache_delete_key = f'*sharable_{root_share_folder.pk}_{file_folder_instance.parentFolder.pk}*'
                else:
                    return Response({"status_code": 5001, "message": "Invalid Parent ID"})
            else:
                file_folder_instance = root_share_folder
                if file_folder_instance.author == user:
                    can_delete = True
                cache_delete_key = f'*sharable_{file_folder_instance.pk}_*'
        
        if can_delete and file_folder_instance:
            file_id = file_folder_instance.imageKit_file_id if not file_folder_instance.isfolder else None # we need the file URL to delete the file from the storage service like S3 or any other service we are using for storing the files because for folders we are not storing any file so we can skip the deletion from the storage service in case of folders.
            if file_folder_instance.is_root: #root records can be only made by the origignal owners......
                print("deleting thr image.........(root)")
                redis_cache.delete_pattern(f'*file_folder_list_{file_folder_instance.author.clerk_user_id}_*', version=2)
            else:
                if cache_delete_key:
                    redis_cache.delete_pattern( cache_delete_key, version=2)  #for deleting the shared instance 
                redis_cache.delete_pattern(f'*file_folder_list_{file_folder_instance.author.clerk_user_id}_{file_folder_instance.parentFolder.pk}*', version=2)  #clearing the cache of the owner(who shared...)
            print(cache_storage_key[0])

            file_folder_instance.delete()
            #updating the storage stats of the user based on the deleted file size
            if root_share_folder:
                print('updating the root_share_folder')
                ClerkUserStorage.objects.filter(author=root_share_folder.author).update(
                            clerk_user_used_storage=F('clerk_user_used_storage') - file_folder_instance.size,
                            total_image_storage=F('total_image_storage') - file_folder_instance.size
                )
            else:
                print('updating the user"s storage stats')
                ClerkUserStorage.objects.filter(author=file_folder_instance.author).update(
                            clerk_user_used_storage=F('clerk_user_used_storage') - file_folder_instance.size,
                            total_image_storage=F('total_image_storage') - file_folder_instance.size
                )


            redis_cache.delete_pattern(cache_storage_key[0], version=1) #deleting the storage capacity....

            if file_id:
                delete_image_from_imagekit.delay(file_id) #deleting the image from the storage service asynchronously using celery to avoid any delay in the API response because of the deletion process from the storage service which can take some time depending on the size of the file and the response time of the storage service. We are passing only the file ID to the celery task to delete the image from the storage service because we can directly delete the image from the storage service using the file ID without needing any other information about the file.

            responce_data = {
            "status_code" : 5000,
            "message" : "Successfully deleted the record",
            "data" : ""
            }
            return Response(responce_data)
    
        else:
            responce_data = {
            "status_code" : 5001,
            "message" : "Can't delete the record",
            "data" : ""
            }
            return Response(responce_data)
    else:
        responce_data = {
            "status_code" : 4001,
            "message" : "User not authenticated",
            "data" : ""
        }
        return Response(responce_data)



# FUNCTIONS FOR MOVE FEATURE..........................................

@api_view(['GET'])
def list_the_possible_folders_to_move(request):
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

        folder_id_hashed = request.query_params.get("hashedFolderID")
        folder_id = hash_ID.decode_id(folder_id_hashed) if folder_id_hashed else None
        all_child_instances = None  #collecting the childs to show
        ordered_breadcrumbs = []

        if folder_id:
            folder_instance = FileFolderModel.objects.filter(pk = folder_id , is_trash=False , author= user).first()
            if folder_instance:
                path = folder_instance.path.split("/") if folder_instance.path else []
                path.append(str(folder_instance.pk))

                queryset = FileFolderModel.objects.filter(pk__in=path).values('id', 'name')
                name_map = {str(item['id']): item['name'] for item in queryset}

                for folder_id in path:
                    if folder_id in name_map:
                        ordered_breadcrumbs.append({
                            "name": name_map[folder_id],
                            "hashed_id": hash_ID.encode_id(int(folder_id)) })
                        
                all_child_instances = FileFolderModel.objects.filter(parentFolder = folder_instance , is_trash=False)
            else:
                responce_data = {
                "status_code" : 5001,
                "message" : "No folder found .....",
                "data" : ""
                }
                return Response(responce_data)
        
        else:
            all_child_instances = FileFolderModel.objects.filter(parentFolder = None , is_trash=False , author = user)  #collects all the root file folders

        context = {
            'request' : request
        }

        serialized_data = ShareChildFileFolderShareSerializer(all_child_instances , many=True , context=context).data

        responce_data = {
            'status_code' : 5000,
            'message' : 'fetched the details',
            'data' : serialized_data,
            'breadcrumb_details' : ordered_breadcrumbs
        }

        return Response(responce_data)
        
    else:
        responce_data = {
            'status_code' : 4001,
            'message' : 'User not authenticated',
            'data' : ''
        }
        return Response(responce_data)

@api_view(['POST'])
def move_file_folder(request):
    # This function is used to move the file folder from one location to another location in the file folder structure and also to move the shared instance of the file folder if it is shared and also to update the cache accordingly for the owner and the shared instance if it is shared.
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


        target_folder_hashed_id = request.query_params.get("targetFolderHashedID") #the place where the record will be moved -> ALWAYS FOLDER , will be none for if its root
        source_record_hashed_id = request.query_params.get("sourceRecordHashedID") #the source (record ) that is to be moved
        

        target_folder_id = hash_ID.decode_id(target_folder_hashed_id) 
        source_record_id = source_record_hashed_id
       

        with transaction.atomic():
            if target_folder_id:  #calculations for placing the Record inside a new folder.
                if source_record_id and target_folder_id != source_record_id:    
                    ids = [int(target_folder_id), int(source_record_id)] 
                    ids = sorted(ids)

                    query_set = FileFolderModel.objects.select_for_update().filter(pk__in=ids, author=user)
                    query_map = {item.pk: item for item in query_set}

                    target_folder_instance = query_map.get(int(target_folder_id)) 
                    source_record_instance = query_map.get(int(source_record_id))

                    if not target_folder_instance.isfolder:  #checking if the provided target record is actually a folder or not because we can move only in folders not in files and if it is not a folder we will return an error message.
                        responce_data = {
                            "status_code" : 5001,
                            "message" : "Invalid Move Operation. It's not a folder",
                            "data" : ""
                        }
                        return Response(responce_data)
                    
                    
                    target_path_list = target_folder_instance.path.split("/") if target_folder_instance.path else []
                    if str(source_record_id) in target_path_list or str(source_record_id) == str(target_folder_id):
                        responce_data = {
                            "status_code": 5001,
                            "message": "Invalid Move. You cannot move a folder into itself or its own subfolder.",
                            "data": ""
                        }
                        return Response(responce_data)

                    #setting the path for the source record based on the new location
                    new_path_for_source = f'{target_folder_instance.path}/{target_folder_instance.pk}' if target_folder_instance.path else f'{target_folder_instance.pk}'
                    
                    old_path_of_source_used_in_child = f'{source_record_instance.path}/{source_record_instance.pk}' if source_record_instance.path else f'{source_record_instance.pk}' #this is used to filter the child records of the source record to update their path based on the new location of the source record after the move operation.


                    search_prefix = f"{source_record_instance.path}/" if source_record_instance.path else ""
                    replace_prefix = f"{target_folder_instance.path}/{target_folder_instance.pk}/" if target_folder_instance.path else f"{target_folder_instance.pk}/"


                    #single SQL quey
                    FileFolderModel.objects.filter(
                        Q(pk=source_record_id) | Q(path__startswith=old_path_of_source_used_in_child)
                    ).update(
                        path=models.Case(
                            models.When(pk=source_record_id, then=Value(new_path_for_source)),
                            default=Replace('path', Value(search_prefix), Value(replace_prefix)),
                            output_field=models.TextField()
                        ),
                        parentFolder=models.Case(
                            # Use the ID (PK), not the instance object
                            models.When(pk=source_record_id, then=Value(target_folder_id) ),
                            default=models.F('parentFolder'),
                            output_field=models.IntegerField() # Use the field type of your PK (usually Integer)
                        ),
                        is_root=models.Case(
                            # For the source, check if we just moved it to Root
                            models.When(pk=source_record_id, then=Value(target_folder_id is None)),
                            # For children, their is_root remains False (they are not root)
                            default=Value(False),
                            output_field=models.BooleanField()
                        )
                    )
                    

                    # CACHE MANAGMENT.........................................

                    redis_cache.delete_pattern(f'*file_folder_list_{source_record_instance.author.clerk_user_id}_{target_folder_id}*', version=2)

                    if source_record_instance.parentFolder:
                        redis_cache.delete_pattern(f'*file_folder_list_{source_record_instance.author.clerk_user_id}_{source_record_instance.parentFolder}*', version=2)
                    else:
                        redis_cache.delete_pattern(f'*file_folder_list_{source_record_instance.author.clerk_user_id}*', version=2)

                    redis_cache.delete_pattern(f'*sharable_{source_record_id}_*' , version=2)
                    redis_cache.delete_pattern(f'*sharable_{target_folder_id}_*' , version=2)


                    responce_data = {
                        'status_code' : 5000,
                        'message' : 'Moved the record successfully',
                        'data' : ''
                    }
                    return Response(responce_data)
            
            else:
                    # used for copying the record to the root structure from any folder because in root structure we dont have any parent folder so we will set the parent folder to null and also update the path to null because path is used to track the parent structure and if there is no parent then there is no need of path and also we need to make sure that the record is not moved to the same location because if we move the record to the same location then there will be no change in the path and it will create a loop in the path which will cause an infinite loop in the code when we try to access the child records of that record because it will keep on adding the same record ID in the path and it will never end and it will cause a crash in the code.
                source_record_instance = FileFolderModel.objects.select_for_update().filter(pk = source_record_id, author=user).first()

                if source_record_instance is None:
                    responce_data = {
                        'status_code' : 5001,
                        'message' : 'Source record not found',
                        'data' : ''
                    }
                    return Response(responce_data)
                

                #setting the path for the source record based on the new location
                new_path_for_source = None
                
                old_path_of_source_used_in_child = f'{source_record_instance.path}/{source_record_instance.pk}' if source_record_instance.path else f'{source_record_instance.pk}' #this is used to filter the child records of the source record to update their path based on the new location of the source record after the move operation.
                search_prefix = f"{source_record_instance.path}/" if source_record_instance.path else ""
                replace_prefix = ""  #since we are making it into root.

                #single SQL quey
                FileFolderModel.objects.filter(
                    Q(pk=source_record_id) | Q(path__startswith=old_path_of_source_used_in_child)
                ).update(
                    path=models.Case(
                        models.When(pk=source_record_id, then=Value(None)), #since we are making it into root so path will be null for the source record and for the child records the path will be updated based on the new location of the source record after the move operation.
                        default=Replace('path', Value(search_prefix), Value(replace_prefix)),
                        output_field=models.TextField()
                    ),
                    parentFolder=models.Case(
                        # Use the ID (PK), not the instance object
                        models.When(pk=source_record_id, then=Value(None)),
                        default=models.F('parentFolder'),
                        output_field=models.IntegerField() # Use the field type of your PK (usually Integer)
                    ),
                    is_root=models.Case(
                        # For the source, check if we just moved it to Root
                        models.When(pk=source_record_id, then=Value(True)),
                        # For children, their is_root remains False (they are not root)
                        default=Value(False),
                        output_field=models.BooleanField()
                    )
                )

                # deleting down the outdated root cache
                redis_cache.delete_pattern(f'*file_folder_list_{source_record_instance.author.clerk_user_id}*', version=2)
                responce_data = {
                    'status_code' : 5000,
                    'message' : 'moved to root successfully',
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

@api_view(['POST'])
def copy_file_folder(request):
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
        
        target_folder_hashed_id = request.query_params.get("targetFolderHashedID") #the place where the record will be moved -> ALWAYS FOLDER , will be none for if its root
        source_record_hashed_id = request.query_params.get("sourceRecordHashedID") #the source (record ) that is to be moved
        sharable_uuid_of_main_resource = request.query_params.get("sharableUUID")

        target_folder_id = hash_ID.decode_id(target_folder_hashed_id)
        source_record_id = source_record_hashed_id if isinstance(source_record_hashed_id , int) else hash_ID.decode_id(source_record_hashed_id) #native user uses there DB ID where as shared will use hashed one which will be decoded

        # Checking the permission status
        if sharable_uuid_of_main_resource:
            share_record = ShareLink.objects.select_related('file_folder_instance').filter(shareable_id=sharable_uuid_of_main_resource).first()
            if not share_record:
                return Response({"status_code": 5001, "message": "You are not assigned to share this." , "data" : ""})
            root_share_folder = share_record.file_folder_instance
            permission_granded = None

            if root_share_folder.author == user:
                permission_granded = ('OWNER' , )
                print('the user requesting to upload is a owner')
            else:
                permission_instance = FileFolderPermission.objects.filter(fileFolder_Instance_id=root_share_folder, user_id=user).first()
                print('collecting the request status of the user')
                if permission_instance:
                    ids = (root_share_folder.path.split("/") if root_share_folder.path else []) + [str(root_share_folder.pk)]
                    permission_granded = permission.grand_permission_for_shared_instance(ids, user, permission_instance)
                    print(f'permission granted for the user is {permission_granded}')
                else:
                    return Response({"status_code": 5001, "message": "Permission Record not found" , "data": ""})
                
            if permission_granded[0] not in ['EDIT' , 'ADMIN', 'OWNER']:
                return Response({"status_code": 5001, "message": "You cant create a copy" , "data": ""})
        
        if source_record_id:
            print(source_record_id , source_record_hashed_id)
            ids = [int(source_record_id)]
            print(ids)
            record_context = FileFolderModel.objects.select_for_update().filter(pk__in=ids)
            record_map = {item.pk: item for item in record_context}
            print(record_map)
            source_record_instance = record_map.get(int(source_record_id))
            print(source_record_instance)
            if source_record_instance is None:
                responce_data = {
                    'status_code' : 5001,
                    'message' : 'Source record not found',
                    'data' : ''
                }
                return Response(responce_data)
            
            required_memory_space = copyToolkit.calculate_total_space_required(source_record_instance) if source_record_instance.isfolder else source_record_instance.size 
            user_storage = ClerkUserStorage.objects.filter(author=user).first()
            if not user_storage:
                responce_data = {
                    'status_code' : 5001,
                    'message' : 'User doesnt have storage record',
                    'data' : ''
                }
                return Response(responce_data)
            
            available_storage_space = user_storage.clerk_user_storage_limit - user_storage.clerk_user_used_storage
            if available_storage_space < required_memory_space:
                responce_data = {
                    'status_code' : 5001,
                    'message' : 'Not enough storage space to copy the record',
                    'data' : ''
                }
                return Response(responce_data)
            
            print("off loading")
            copy_engine = implement_copy_of_records.delay(source_record_id , target_folder_id , required_memory_space , user.clerk_user_id )
            print("off loading")
            responce_data = {
                'status_code' : 5000,
                'message' : 'Added to the queue system , will be copied in sometimes',
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
       
@api_view(['POST'])
def search_file_folders(request):
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
        
        user_search_query =  request.query_params.get("q")
        queryset = None
        scope_of_search = request.query_params.get("scope")
        if scope_of_search:  # for searching of the sub folder structures 
            queryset = FileFolderModel.objects.filter(author = user , parentFolder = scope_of_search)
        else: #if no scope that performing global search
            queryset = FileFolderModel.objects.filter(author=user)

        if user_search_query and queryset:
            search_query_vector = SearchQuery(user_search_query , search_type="websearch")  #this function converts the query from the user to a format that it can be similar to the search_vector field
            queryset = queryset.annotate(
                rank = SearchRank(F('search_vector') , search_query_vector , cover_density=True , normalization=32),
                snippet = SearchHeadline(
                    Coalesce('description' , Value('')),
                    search_query_vector,
                    start_sel="<mark className='text-red-500 font-bold font-figtree'>",
                    stop_sel="</mark>",
                )
            ).filter(search_vector = search_query_vector).order_by('-rank','-isfolder')
            context = {
                "request" : Request
            }
            serialized_data = SearchResultSerializer(queryset , many=True , context=context).data
            
            responce_data = {
                    "status_code" : 5000,
                    "message" : "Successfully Searched the content you need",
                    "data" : serialized_data
            }
            return Response(responce_data)
        
        responce_data = {
                    "status_code" : 5001,
                    "message" : "no query found",
                    "data" : ""
            }
        return Response(responce_data)

    else:
        responce_data = {
            'status_code' : 4001,
            'message' : 'User not authenticated',
            'data' : ''
        }
        return Response(responce_data)

@api_view(['POST'])
def check_password_return_session_token(request):
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
        
        password_to_check = request.data.get('password')  #getting the password from the frontend to check with the encrypted password in the db
        file_folder_id = request.query_params.get('fileFolderID') #getting the file folder ID to check the password for that specific file folder instance
        
        if file_folder_id:
            if file_folder_id.isdigit():
                file_folder_id = int(file_folder_id)  # Convert to integer if it's a digit
            else:
                file_folder_id = hash_ID.decode_id(file_folder_id) #used to decode the hashed ID if the shared resource is been tried 
            
        file_folder_instance = FileFolderModel.objects.filter(pk=file_folder_id).first() #fetching the file folder instance from the db based on the provided ID
        security_policy_instance = ResourceSecurityPolicies.objects.filter(file_folder_instance=file_folder_instance).first() #fetching the security policy instance for that file folder instance to get the encrypted password to check with the password provided from the frontend        
        if not file_folder_instance or not security_policy_instance:
            responce_data = {
                'status_code' : 5001,
                'message' : 'Record / security instance not found',
                'data' : ''
            }
            return Response(responce_data)
        
        is_locked = security_policy_instance.is_locked # feature that bypasses the session validation and direclty prompts for password each time.
        print(password_to_check , file_folder_id)

        if check_password(password_to_check , security_policy_instance.encypted_password or ""):
            print("inside the password check")
            #Generating the sesssion token key which will be valid for 5 minutes.
            random_security_token_string = str(uuid.uuid4())  #creating unique uuid 32 bit string
            if not is_locked: # this block will be executed only for session managment since in is_locked session is not required to be stored.
                hashed_security_token_string = make_password(random_security_token_string) #hashing the random string to store in the db as a session token for security purposes because we dont want to store the raw token in the db for security reasons.
                security_session , created = SecuritySession.objects.update_or_create(
                    session_user = user,
                    file_folder_instance = file_folder_instance,
                    defaults={'session_token': hashed_security_token_string, 'expiry_time': timezone.now() + timedelta(minutes=security_policy_instance.session_duration), 'created_at_or_updated_at': timezone.now()},
                    create_defaults={'session_user' : user , 'file_folder_instance' : file_folder_instance, 'session_token': hashed_security_token_string, 'created_at_or_updated_at': timezone.now(), 'expiry_time': timezone.now() + timedelta(minutes=security_policy_instance.session_duration)}
                )

            responce_data = {
                'status_code' : 5000,
                'message' : 'Entered the correct password and session token created successfully',
                'data' : ''
            }

            responce =  Response(responce_data)
            print(f'file_access_{file_folder_id}')
            responce.set_cookie(
                key=f'short_time_access_{file_folder_id}' if is_locked else f'file_access_{file_folder_id}', 
                value=random_security_token_string,
                httponly=True,           # Prevents JS access (XSS protection)
                secure=False,             # Ensures it's only sent over HTTPS (currenlty I am in local development so false to allow http request)
                samesite='Lax',          # CSRF protection
                max_age=10 if is_locked else 3600,            # 1 hour in seconds
                # domain="localhost"     # Optional: specify if needed for local dev
                path='/'
            )
            print("cooked the cokkies")
            return responce
            
        responce_data = {
            'status_code' : 5009,
            'message' : 'Wrong password !, Please enter the correct password to access this resource',
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
    

@api_view(['POST'])
def create_or_update_security_policy(request):
    "This API can only be handled by the Owners , no matter about the share permission or anything , since its a policy only author can access this endpoint."
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
        
        file_folder_id = request.query_params.get('fileFolderID')
        if file_folder_id:
            if file_folder_id.isdigit():
                file_folder_id = int(file_folder_id)  # Convert to integer if it's a digit
            else:
                file_folder_id = hash_ID.decode_id(file_folder_id) #used to decode the hashed ID if the shared resource is been tried 
            
        file_folder_instance = FileFolderModel.objects.filter(pk=file_folder_id , author=user).first()
        if not file_folder_instance:
            responce_data = {
                'status_code' : 5001,
                'message' : 'Record instance not found',
                'data' : ''
            }
            return Response(responce_data)
       
        with transaction.atomic():  #ensuring that all works or fails together to avoid bottlenecks.
            security_policy_instance , created = ResourceSecurityPolicies.objects.get_or_create(
                file_folder_instance=file_folder_instance,
                defaults={'file_folder_instance': file_folder_instance, 'encypted_password': None}
                )

            if 'password' in request.data:
                password_to_set = request.data.get('password') #getting the password from the frontend to encrypt and store in the db
                if password_to_set:
                   security_policy_instance.encypted_password = make_password(password_to_set)

            if 'is_password_protected' in request.data or 'is_security_critical' in request.data or 'is_locked' in request.data or 'session_duration' in request.data:
                is_password_protected = request.data.get('is_password_protected') #getting the boolean value from the frontend to set the is_password_protected field in the db which will be used to check if the password protection is enabled for that file folder instance or not when someone tries to access that resource.  (boolean)
                is_security_critical = request.data.get('is_security_critical') #used to decide whether to bypass the author. (boolean)
                is_locked = request.data.get('is_locked')
                session_duration = request.data.get('session_duration')

                if is_password_protected is not None:
                    if not is_password_protected:
                        security_policy_instance.encypted_password = None #if the password protection is being disabled then we will set the encrypted password to null because there is no need to keep the old encrypted password when the password protection is disabled because it can cause confusion in the future if we keep the old encrypted password when the password protection is disabled and if someone enables the password protection again then it will use the old encrypted password which can cause security issues because the old encrypted password can be compromised and if we keep it null then there will be no security issues because when someone enables the password protection again then it will require to set a new password and it will create a new encrypted password in the db which will be more secure than keeping the old encrypted password in the db when the password protection is disabled.
                    security_policy_instance.is_password_protected = is_password_protected
                
                if is_security_critical is not None:
                    security_policy_instance.is_critical = is_security_critical
                
                if is_locked is not None:
                    security_policy_instance.is_locked = is_locked
                
                if session_duration is not None:
                    security_policy_instance.session_duration = session_duration
                
                security_policy_instance.save(update_fields=['is_password_protected', 'is_critical' , 'encypted_password' , 'is_locked' , 'session_duration'])
                responce_data = {
                    'status_code' : 5000,
                    'message' : 'Security policy updated successfully',
                    'data' : ''
                }
                return Response(responce_data)
            
            security_policy_instance.save(update_fields=['encypted_password'])
            responce_data = {
                'status_code' : 5000,
                'message' : 'Security policy updated successfully',
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



@api_view(['GET'])
def get_security_policy(request):
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
        
        file_folder_id = request.query_params.get('fileFolderID')
        if file_folder_id:
            if file_folder_id.isdigit():
                file_folder_id = int(file_folder_id)  # Convert to integer if it's a digit
            else:
                file_folder_id = hash_ID.decode_id(file_folder_id) #used to decode the hashed ID if the shared resource is been tried 
                
        # we need to return current stae of the secuirty policies.
        security_policy_instance = ResourceSecurityPolicies.objects.select_related('file_folder_instance').filter(file_folder_instance__id=file_folder_id).first()
        if not security_policy_instance:
            responce_data = {
                'status_code' : 5001,
                'message' : 'Security policy not found',
                'data' : ''
            }
            return Response(responce_data)
        
        context = {
            "request" : Request
        }
        serialized_data = SecurityPolicySerializer(security_policy_instance , context = context).data
        responce_data = {
            'status_code' : 5000,
            'message' : 'Fetched the security policy details successfully',
            'data' : serialized_data
        }
        return Response(responce_data)
    else:
        responce_data = {
            'status_code' : 4001,
            'message' : 'User not authenticated',
            'data' : ''
        }
        return Response(responce_data)