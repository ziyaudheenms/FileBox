import os
import base64
import shutil
from sqlite3 import Cursor
from tkinter import NO, TRUE
from attr import has
from click import File
from django.db import transaction
from django.contrib.auth.hashers import make_password, check_password
from django.db.models import F
from django.core.exceptions import ValidationError
# importing django cache system 
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django_redis.cache import RedisCache

#importing the dotenv packages and rest framework packages 
from django.conf import settings
from dotenv import load_dotenv
from rest_framework.response import Response
from rest_framework.decorators import api_view

# pakckages for clerk integration
from clerk_backend_api import Clerk, Instance
from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions

#packages for imagekit integration
from imagekitio import ImageKit

#importing the queue tasks for Celery to work on with
from Backend.tasks import upload_image_to_imagekit

#importing the ratelimiting fuctions
from django_smart_ratelimit import rate_limit
from django_ratelimit.decorators import ratelimit

from Backend.models import ClerkUserStorage, FileFolderModel, ClerkUserProfile, FileFolderPermission, ShareLink # importing the models from the registered app
from Backend.ratelimit import get_user_tier_based_rate_limit , get_user_role_or_ip, get_user_tier_based_rate_limit_for_chunking_of_files
from .serializers import FileFolderSerializer, FileFolderShareSerializer, UserStorageSerializer, PermissionUserSerializer
from .pagination import FileFolderCursorBasedPagination  #custom pagination class for file/folder GET API responce


load_dotenv()
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
        # print(request)
        file = request.data['image']
        print(file)
        file_bytes = file.read()
        file_base64 = base64.b64encode(file_bytes).decode('utf-8')
        filename = file.name
        filesize = file.size
        filename_with_extension = file.name
        root , extension = os.path.splitext(filename_with_extension)

        user = ClerkUserProfile.objects.get(clerk_user_id = user_id)
        folder = None #initializing the parent folder.
        if folder_name_info is not None:
            if FileFolderModel.objects.filter(pk = folder_name_info).exists():
                folder = FileFolderModel.objects.get(pk = folder_name_info)
            else:
                folder = None

        #creating the dummy record for reference in the frontend()
        file_instance = FileFolderModel.objects.create(
            author = user,
            name = filename,
            size = filesize,
            is_root = True if folder == None else False,
            parentFolder = folder,
            file_url = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTEpYntNMtkoBOau-IFwoq7wUlivz4VfNir9g&s",
            file_extension = extension,
            celery_task_ID = 1
        )
        #task is queued to work at offload , so that to avoid the smooth fuctioning of api and workflow of the system.
        print(file_instance.pk)
        if file_instance.is_root:
            print("deleting thr image.........(root)")
            redis_cache.delete_pattern(f'*file_folder_list_{user.clerk_user_id}_*', version=2)
        else:
            print("deleting thr image.........")
            redis_cache.delete_pattern(f'*file_folder_list_{user.clerk_user_id}_{file_instance.parentFolder.pk if file_instance.parentFolder != None else None}*', version=2)

        queue_worker = upload_image_to_imagekit.delay(filename , file_base64 , file_instance.pk)

        file_instance.celery_task_ID = queue_worker.id
        file_instance.save()
    
        responce_data = {
            "status_code" : 5000,
            "message" : "Image Added to Queue Successfully, Upload Started",
            "data" : file_instance.pk
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
        file_name = request.data["fileName"]
        file_size = request.data["fileSize"]
        file_extenstion = request.data["fileExtenstion"]

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
        #creating the dummy record for reference in the frontend()
        file_instance = FileFolderModel.objects.create(
            author = user,
            name = file_name,
            size = file_size,
            is_root = True if folder == None else False,
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

        print(folder_name_info)

        folder = None #initializing the parent folder.
        if folder_name_info is not None:
            if FileFolderModel.objects.filter(pk = folder_name_info).exists():
                folder = FileFolderModel.objects.get(pk = folder_name_info)
            else:
                print("haloo")
                folder = None

        print(folder)


        folder_instance = FileFolderModel.objects.create(
            author = user,
            name = folder_name,
            size = 0,
            isfolder = True,
            is_root = True if folder == None else False,
            parentFolder = folder,
            upload_status = "UPLOADED"
        )
        
        responce_data = {
                "status_code" : 5000,
                "message" : "Fodler Created Successfully",
                "data" : folder_instance.pk
            }

        
        redis_cache: RedisCache = cache # type: ignore
        if folder_name_info is None:
            redis_cache.delete_pattern(f'*file_folder_list_{user.clerk_user_id}_*', version=2)
        else:
            redis_cache.delete_pattern(f'*file_folder_list_{user.clerk_user_id}_{folder_name_info}*', version=2)

        return Response(responce_data)
    else:
        responce_data = {
            "status_code" : 4001, 
            "message" : "User not authenticated",
            "data" : ""
        }
        return Response(responce_data)


@api_view(['DELETE'])
@ratelimit(key=lambda g, request: get_user_role_or_ip(g, request), rate=lambda g, request: get_user_tier_based_rate_limit(g, request) , block=True)  #used for getting the rate limiting based on the teir of the user
@rate_limit(key=lambda g, request: get_user_role_or_ip(g, request), rate='100/m', block=True, algorithm='token_bucket',algorithm_config={
        'bucket_size': 200,  # Allow bursts up to 200 requests
        'refill_rate': 2.0,  # Refill at 2 tokens per second
})  # used for implementing token bucket algorithm for rate limiting
def deleteFolderFile(request):
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
            instance_to_delete = FileFolderModel.objects.get(pk=folder_file_id, author = user)
            instance_to_delete.delete()

            responce_data = {
                "status_code" : 5000,
                "message" : "Fodler/File deleted Successfully",
                "data" : ""
            }
            return Response(responce_data)
        else:
            responce_data = {
                "status_code" : 5002,
                "message" : "Fodler Not Found",
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
def getAllFileFolders(request):
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

        # redis_cache: RedisCache = cache # type: ignore
        # redis_cache.delete_pattern(f'storage_stat_of_{user.clerk_user_id}*', version=1)
        cache_key = f'file_folder_list_{user.clerk_user_id}_{parent_folder_id}_{pagination_cursor}' # setting the Cache Key for the specific user and parent folder ID and pagination cursor to look up in the cache.

        print('Generated Cache Key', cache_key)

        #looking up in cache for the required data.
        if cache.has_key(cache_key , version=2):
            print('Fetching from cache version 2', cache_key)
            return Response(cache.get(cache_key , version=2))
        

        if parent_folder_id is not None:
            all_files_folders_instance = FileFolderModel.objects.filter(is_trash = False , parentFolder = parent_folder_id , author = user).order_by('-updated_at')
        else:
            all_files_folders_instance = FileFolderModel.objects.filter(is_trash = False , is_root = True , author = user).order_by('-updated_at')

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
            print("setting the cached value")
            return paginated_files_folders.get_paginated_response(serialized_files_and_folders.data)
        
        serialized_files_and_folders = FileFolderSerializer(all_files_folders_instance, many = True , context = context)
        print(serialized_files_and_folders.data , cache_key , "OUTSIDE THE PAGINATION CLASS.....")
        responce_data = {
                "status_code" : 5000,
                "message" : "Folder Created Successfully",
                "data" : serialized_files_and_folders.data
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
def getSingleImage(request):
    #API enpoint to get single image details based on the image ID passed through the query params
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
        
        image_file_id = request.query_params.get("imageFileID")   #get the ID of the image file through query params

        if FileFolderModel.objects.filter(pk = image_file_id , author = user , isfolder = False).exists():
            image_instance = FileFolderModel.objects.get(pk = image_file_id , author = user , isfolder = False)
            context = {
                "request" : request
            }
            serialized_image = FileFolderSerializer(image_instance , context = context)

            responce_data = {
                "status_code" : 5000,
                "message" : "Image Fetched Successfully",
                "data" : serialized_image.data
            }

            return Response(responce_data)
        else:
            responce_data = {
                "status_code" : 5002,
                "message" : "Image Not Found",
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

        user = ClerkUserProfile.objects.get(clerk_user_id = user_id)
        if not user:
            responce_data = {
                "status_code" : 4001,
                "message" : "User Record Not Found",
                "data" : ""
            }
            return Response(responce_data)
        
        storage_cache_key = f'storage_stat_of_{user_id}'
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
        
        fileFolderID = request.query_params.get("fileFolderID")

        if FileFolderModel.objects.filter(pk = fileFolderID).exists():
            file_instance = FileFolderModel.objects.get(pk= fileFolderID)
            if file_instance.author != user:
                responce_data = {
                    "status_code" : 5003,
                    "message" : "You Have No Rights To Access This Data",
                    "data" : ""
                }
                return Response(responce_data)

            data = request.data['usersToGrandPermission']  #Array of objects that contains the emai and permission.
            try:
                with transaction.atomic():
                    for item in data:
                        email = item['email'].strip()
                        permission = item['permission'].strip()

                        if permission not in ['VIEW' , 'EDIT' , 'ADMIN']:
                            responce_data = {
                                "status_code" : 5002,
                                "message" : "The Given User Role Doesnt Exists !",
                                "data" : ""
                            }
                            return Response(responce_data)
                        
                        if not ClerkUserProfile.objects.filter(clerk_user_email = email).exists():
                            responce_data = {
                                "status_code" : 5002,
                                "message" : "UserNot Found To Be Assigned With Permission!",
                                "data" : ""
                            }
                            return Response(responce_data)

                        #we dont need to create a permission class for the author , there for verfifying that using a if clause.
                        if email != user.clerk_user_email:
                            FileFolderPermission.objects.update_or_create(
                            fileFolder_Instance_id = file_instance,
                            user_id = ClerkUserProfile.objects.get(clerk_user_email = email),
                            defaults= {"permission_type" : permission},
                            create_defaults = {
                                'fileFolder_Instance_id' : file_instance,
                                'user_id' : ClerkUserProfile.objects.get(clerk_user_email = email),
                                'permission_type' : permission
                            }
                        )
                                                    
                responce_data = {
                    "status_code" : 5000,
                    "message" : "Successfully Updated the permissions..",
                    "data" : ""
                }
           
                redis_cache.delete_pattern(f'*users_with_permission_{fileFolderID}*', version=2)

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
        
        fileFolderID = request.query_params.get("fileFolderID")
        if not FileFolderModel.objects.filter(pk = fileFolderID).exists():
            responce_data = {
                "status_code" : 5002,
                "message" : "Opps ! FileFolder Record not found",
                "data" : ""
            }
            return Response(responce_data)
        
        user_with_access_cache_key = f"users_with_permission_{fileFolderID}"
        if cache.has_key(user_with_access_cache_key , version=2):
            print("collecting from permission cache....")
            return Response(cache.get(user_with_access_cache_key , version=2))


        file_instance = FileFolderModel.objects.get(pk=fileFolderID)
        try:
            permitted_users_instance = FileFolderPermission.objects.filter(fileFolder_Instance_id = file_instance)
            serialized_data = []
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
                "status_code" : 5002,
                "message" : "Permission Record doesnt found",
                "data" : ""
            }
            return Response(responce_data)
        except Exception as e:
            responce_data = {
                "status_code" : 5000,
                "message" : "Successfully Updated the permissions..",
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

        if not FileFolderModel.objects.filter(pk = file_folder_id).exists():
            responce_data = {
                "status_code" : 5002,
                "message" : "Record not Found",
                "data" : ""
            }
            return Response(responce_data)
        
        file_folder_instance = FileFolderModel.objects.get(pk = file_folder_id)

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
                "message" : "Acess Option is not Found",
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
        # if not ShareLink.objects.filter(shareable_id = sharable_uuid).exists():
        #     responce_data = {
        #         "status_code" : 5002,
        #         "message" : "FileFolder Instance Not Found.",
        #         "data" : ""
        #     }
        #     return Response(responce_data)
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
        is_owner = True if share_link_instance.file_folder_instance.author == user else False

        #Skipping all the checks and conditions for the OWNER......
        if not is_owner:
            if not share_link_instance.is_active:
                responce_data = {
                    "status_code" : 5002,
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
                permission_data = {
                    "permission_type" : file_permission_instance.permission_type,
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
        serialized_data = FileFolderShareSerializer(share_link_instance.file_folder_instance , context=context)
        data = serialized_data.data #getting the first elemt (we have only first...)
        print(data)
        if permission_data:
            data['permission_data'] = permission_data
        
        return Response({
            "status_code": 5000,
            "message": "Successfully fetched resource",
            "data": data
            })
    else:
        responce_data = {
            "status_code" : 4001,
            "message" : "User not authenticated",
            "data" : ""
        }
        return Response(responce_data)