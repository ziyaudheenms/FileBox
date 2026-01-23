import os
import base64
import shutil

#importing the dotenv packages and rest framework packages 
from django.conf import settings
from dotenv import load_dotenv
from rest_framework.response import Response
from rest_framework.decorators import api_view

# pakckages for clerk integration
from clerk_backend_api import Clerk
from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions

#packages for imagekit integration
from imagekitio import ImageKit

#importing the queue tasks for Celery to work on with
from Backend.tasks import upload_image_to_imagekit

from django_smart_ratelimit import rate_limit
from django_ratelimit.decorators import ratelimit
from Backend.models import FileFolderModel, FileModel , ClerkUserProfile       # importing the models from the registered app
from Backend.ratelimit import get_user_tier_based_rate_limit , get_user_role_or_ip, get_user_tier_based_rate_limit_for_chunking_of_files
from .serializers import FileFolderSerializer
from .pagination import FileFolderCursorBasedPagination  #custom pagination class for file/folder GET API responce


load_dotenv()
clerk_SDK = Clerk(bearer_auth=os.getenv("CLERK_API_KEY"))  


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
        folder_name_info = request.query_params.get("folderID")
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
                "status_code" : 5001,
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


@api_view(["PATCH"])
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
        folder_file_id = int(request.query_params.get("folderFileID"))

        if FileFolderModel.objects.filter(pk=folder_file_id , author = user).exists():
            instance = FileFolderModel.objects.get(pk=folder_file_id, author = user)
            instance.is_trash = False if instance.is_trash else True  # Updating the trash status based on its current state
            instance.save()

            responce_data = {
                "status_code" : 5000,
                "message" : "Fodler/File Updated Successfully",
                "data" : ""
            }
            return Response(responce_data)
        else:
            responce_data = {
                "status_code" : 5001,
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


@api_view(["PATCH"])
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

        user = ClerkUserProfile.objects.get(clerk_user_id = 'user_353xuTbj5fknTSFSWwNld8bzQdj')  #getting the authenticated author who is creating the folder  
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
            return Response(responce_data)
        else:
            responce_data = {
                "status_code" : 5001,
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
                "status_code" : 5001,
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