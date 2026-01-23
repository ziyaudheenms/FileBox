import base64
import io
from celery import shared_task
from imagekitio import ImageKit

from Backend.models import FileFolderModel, FileModel

@shared_task
def upload_image_to_imagekit(filename , filebase64 , file_modelID):

    try:
        print("Event Started to be uploaded")
        print(file_modelID)
        file_instance = FileFolderModel.objects.get(pk = file_modelID)  #getting the db record to where we have to update the image data
        file_instance.upload_status = 'PROCESSING'  # updating the status
        file_instance.save()
        print("Updated the status of DB Record")
    except FileModel.DoesNotExist:
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
        if uploaded_image and uploaded_image.url:
            file_instance.file_url = uploaded_image.url
            file_instance.size = int(uploaded_image.size / 1024)    #Converting the size of the image into kbs
            file_instance.upload_status = 'UPLOADED'   # Updating the status of the Image
            file_instance.save()

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
        file_instance.save()
        print("Try Again Later !")
        return {
                "status_code" : 5001,
                "message" : "Image Upload Failed",
                "data" : "",
            }