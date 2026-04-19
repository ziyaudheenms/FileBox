import copy
import os
import random
import string
from celery import shared_task
from imagekitio import ImageKit
from Backend.models import ClerkUserProfile, ClerkUserStorage, FileFolderModel
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.db.models import F
from django.core.cache import cache
from django_redis.cache import RedisCache
from dotenv import load_dotenv
from django.db import transaction
from celery.signals import task_prerun , task_postrun
from django.db import close_old_connections
from imagekitio.exceptions import InternalServerException 
from celery.exceptions import MaxRetriesExceededError
load_dotenv()
redis_cache: RedisCache = cache # type: ignore



#Initializing the imagekit SDK
imagekit = ImageKit(
    private_key=os.getenv("IMAGEKIT_PRIVATE_KEY"),
    public_key=os.getenv("IMAGEKIT_PUBLIC_KEY"),
    url_endpoint=os.getenv("IMAGEKIT_URL_ENDPOINT")
)

@shared_task(bind=True, max_retries=3)
def upload_image_to_imagekit(self,filename,filebase64,file_modelID,delete_cache_key,shared_instance_owner):
    try:
        print("Event Started to be uploaded")
        print(file_modelID)
        file_instance = FileFolderModel.objects.get(pk = file_modelID)  #getting the db record to where we have to update the image data
        file_instance.upload_status = 'PROCESSING'  # updating the status
        file_instance.save()
        print("Updated the status of DB Record")
    except FileFolderModel.DoesNotExist:
        return {
                "status_code" : 5001,
                "message" : "Data Record Not Found",
                "data" : "",
        }
    
    try:
        print("Initializing the imagekit SDK")
        print("Trying to Upload the image")
        #Uploading the image to imagekit SDK
        
        uploaded_media = imagekit.upload(
            file=filebase64,
            file_name=filename,
        )
        status_code = uploaded_media.response_metadata.http_status_code
     
        #implementing the retry for imagekit server issues 
        if status_code in [500, 502, 503, 504 ,429]:
            try:
                raise self.retry(countdown=60)
            except MaxRetriesExceededError:
                file_instance.upload_status = 'FAILED'
                file_instance.size = 0
                file_instance.save()
                print("Retry limit exceeded , Try Again Later !")
                return {
                "status_code" : 5001,
                "message" : "Image Upload Failed",
                "data" : "",
                }

        print("Uploaded the image and waiting to get the result")
        print(uploaded_media.url)
        if uploaded_media and uploaded_media.url:
            with transaction.atomic():
                file_instance.file_url = uploaded_media.url
                file_instance.size = int(uploaded_media.size / 1024)    #Converting the size of the image into kbs
                file_instance.upload_status = 'UPLOADED'   # Updating the status of the Image
                file_instance.imageKit_file_id = uploaded_media.file_id
                file_instance.save(update_fields=[
                    'file_url', 'size', 'upload_status', 'imageKit_file_id'
                ])
                # updating the storage stats of the user based on the uploaded file size
                if shared_instance_owner:
                    if ClerkUserStorage.objects.filter(author=shared_instance_owner).exists():
                        ClerkUserStorage.objects.filter(author=shared_instance_owner.author).update(
                            clerk_user_used_storage=F('clerk_user_used_storage') + file_instance.size,
                            total_image_storage=F('total_image_storage') + file_instance.size
                        )
                        redis_cache.delete_pattern(f'*storage_stat_of_{shared_instance_owner}*', version=1)  #clearing the storage of the actually owner's storage where the file sits............
                    else:
                        print("Storage instance not found for the user")

                else:                
                    if ClerkUserStorage.objects.filter(author=file_instance.author).exists():
                        ClerkUserStorage.objects.filter(author=file_instance.author).update(
                            clerk_user_used_storage=F('clerk_user_used_storage') + file_instance.size,
                            total_image_storage=F('total_image_storage') + file_instance.size
                        )
                        redis_cache.delete_pattern(f'*storage_stat_of_{file_instance.author.clerk_user_id}*', version=1)  #clearing the storage of the actually owner's storage where the file sits............
                    else:
                        print("Storage instance not found for the user")

                #setting up the websocket channel layer
                channel_layer = get_channel_layer()
                #cache clearing function
                def clear_cache_layer():
                    if file_instance.is_root:
                        redis_cache.delete_pattern(f'*file_folder_list_{file_instance.author.clerk_user_id}_*', version=2)
                    else:
                        if delete_cache_key:
                            redis_cache.delete_pattern( delete_cache_key, version=2)
                        redis_cache.delete_pattern(f'*file_folder_list_{file_instance.parentFolder.author.clerk_user_id if file_instance.parentFolder else None}_{file_instance.parentFolder.pk if file_instance.parentFolder != None else None}*', version=2)  #clearing the cache of the owner(who shared...)
               
                # clearing the cache data
                transaction.on_commit(clear_cache_layer)

                #using the transaction.on_commit so that to trigger the websocket connection only when the transaction success and saves the DB.
                transaction.on_commit(lambda:async_to_sync(channel_layer.group_send)(
                    f'file_updates_{file_instance.author.pk}', # connecting the channel to the private group of the respective author of the file.
                    {
                        "type" : "send_file_update",  # specifies the particular method in the class of the group we mentioned that is to be called to send real time data to the frontend
                        "file_id" : file_instance.pk,
                        "status" : file_instance.upload_status,
                        "file_url" : file_instance.file_url,
                    }
                ))
                
            return {
                "status_code" : 5000,
                "message" : "Image Successfully Uploaded",
                "data" : "",
            }
        else:
            raise Exception("Some error occured with uploading the image")
        
    except Exception as e:
        print("Sorry ! Some error occured")
        file_instance.upload_status = 'FAILED'
        file_instance.size = 0
        file_instance.save()
        print("Try Again Later !")
        return {
                "status_code" : 5001,
                "message" : "Image Upload Failed",
                "data" : "",
            }



@shared_task
def delete_image_from_imagekit(imagekit_file_ID):
    if imagekit_file_ID:
        try:
            if FileFolderModel.objects.filter(imageKit_file_id = imagekit_file_ID).exists():   #Since I am implemeting the copy functionality , there may be chances that more copies contain same url , so will delete the url only when no file is present 
                print('there is a record which points to this image_kit_ID')
            else:
                imagekit.delete_file(imagekit_file_ID)
                print('successfully deleted the image from the storage service')
        except Exception as e:
            print("Error occured while deleting the image from the storage service", e)
            print(e)
    

@shared_task
def implement_copy_of_records(children_of_current_source_instance_id , target_level_id , storage_space_required , author_id ):

    target_folder_instance = FileFolderModel.objects.filter(pk = target_level_id).first() if target_level_id else None
    child = FileFolderModel.objects.filter(pk = children_of_current_source_instance_id).first()
    author = ClerkUserProfile.objects.filter(clerk_user_id = author_id).first()
  
    if not author:
        return {"status_code": 5001, "message": "User profile not found"}
        
    print(target_folder_instance , child , author)

    with transaction.atomic():
        print("entered")
        def recursive_record_copy(child_instance , target_parent): 
            print("starting")
            copied_instance = copy.copy(child_instance)
            copied_instance.pk = None
            copied_instance.author = author
            print("set the path")
            new_path = f"{target_parent.path or ''}/{target_parent.pk}".strip("/") if target_parent else None
            copied_instance.path = new_path
            copied_instance.parentFolder = target_parent
            copied_instance.is_root = True if target_parent is None else False
            print("set the essential details")
            if FileFolderModel.objects.filter(parentFolder = target_parent , name = child_instance.name).exists():
                random_suffix = ''.join(random.choices(string.digits, k=4))
                copied_instance.name = child_instance.name + f"_{random_suffix}"
                print("set the updatde name")
            else:
                copied_instance.name = child_instance.name 
                print("set the stick with old name")
            copied_instance.save()

            if child_instance.isfolder:
                print("set the grandcho=ild")
                grandchildren = FileFolderModel.objects.filter(parentFolder = child_instance)
                for grandchild in grandchildren:
                    print(grandchild)
                    recursive_record_copy(grandchild , copied_instance)

        
        recursive_record_copy(child , target_folder_instance)

        
        if ClerkUserStorage.objects.filter(author=author).exists():       
            ClerkUserStorage.objects.filter(author=author).update(
                clerk_user_used_storage=F('clerk_user_used_storage') + storage_space_required,
                total_image_storage=F('total_image_storage') + storage_space_required
            )
            redis_cache.delete_pattern(f'*storage_stat_of_{author_id}*', version=1)  #clearing the storage of the actually owner's storage where the file sits............
        else :
            return {
                "status_code" : 5001,
                "message" : "storage instance not found",
                "data" : "",
            }
        
        if target_level_id:
            redis_cache.delete_pattern(f'*file_folder_list_{author_id}_{target_level_id}*', version=2)  #clearing the specific folder
        else:
            redis_cache.delete_pattern(f'*file_folder_list_{author_id}*', version=2)  #clearing the rooot
        
        return {
                "status_code" : 5000,
                "message" : "Image Successfully Uploaded",
                "data" : "",
            }
    

    

    

    
    