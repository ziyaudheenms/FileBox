import base64
import io
from turtle import st
from celery import shared_task
from imagekitio import ImageKit
from Backend.models import ClerkUserProfile, ClerkUserStorage, FileFolderModel
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.db.models import F

@shared_task
def upload_image_to_imagekit(filename , filebase64 , file_modelID):

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
        #Initializing the imagekit SDK
        imagekit = ImageKit(
        private_key='private_ugNvkxKX0QyRm6GxSayXwmHN/Nc=',
        public_key='public_n2oE0DAKbwzawEUN8Jr5nZgZerg=',
        url_endpoint="https://ik.imagekit.io/ijp7dfuzp"
        )
        print("Trying to Upload the image")
        #Uploading the image to imagekit SDK
        uploaded_image = imagekit.upload(
            file=filebase64,
            file_name=filename,
        )
        print("Uploaded the image and waiting to get the result")
        print(uploaded_image.url)
        if uploaded_image and uploaded_image.url:
            file_instance.file_url = uploaded_image.url
            file_instance.size = int(uploaded_image.size / 1024)    #Converting the size of the image into kbs
            file_instance.upload_status = 'UPLOADED'   # Updating the status of the Image
            file_instance.save()
            # updating the storage stats of the user based on the uploaded file size
            if ClerkUserStorage.objects.filter(author=file_instance.author).exists():
                ClerkUserStorage.objects.filter(author=file_instance.author).update(
                    clerk_user_used_storage=F('clerk_user_used_storage') + file_instance.size,
                    total_image_storage=F('total_image_storage') + file_instance.size
                )
            else:
                print("Storage instance not found for the user")

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'file_updates_{file_instance.author.pk}', # connecting the channel to the private group of the respective author of the file.
                {
                    "type" : "send_file_update",  # specifies the particular method in the class of the group we mentioned that is to be called to send real time data to the frontend
                    "file_id" : file_instance.pk,
                    "status" : file_instance.upload_status,
                    "file_url" : file_instance.file_url,
                }
            )
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