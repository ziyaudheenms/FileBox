from email.mime import image
from pyexpat import model
from django.db import models

# Create your models here.


class ClerkUserProfile(models.Model):

    TIER_OPTIONS = [
        ('FREE', 'Free'),
        ('PRO', 'Pro'),
        ('ADVANCED', 'Advanced'),
        ]
    clerk_user_id = models.TextField(null=False , unique=True , db_index=True)  #used for fast fetching of the clerkID without the need of scanning the entire Database.
    clerk_user_name = models.TextField(null=False)
    clerk_user_email = models.EmailField(null=False)
    clerk_user_created_at = models.DateTimeField(auto_now_add=True)
    clerk_user_updated_at = models.DateTimeField(auto_now=True)
    clerk_user_tier = models.CharField(max_length=50 , null=False , choices=TIER_OPTIONS , default='FREE')

    def __str__(self) -> str:
        return self.clerk_user_name
    

class FileFolderModel(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('UPLOADED', 'Uploaded'),
        ('FAILED', 'Failed'),
    ]
    #All the comman record field to be collected regardless of if it's a file/folder
    author = models.ForeignKey(ClerkUserProfile, on_delete=models.CASCADE, related_name="user")
    name = models.TextField(null=False)
    size = models.BigIntegerField(null=False , default=0) #if the data record is folder , we will dynamically set the size in the  serializer.
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    isfolder = models.BooleanField(default=False) # Used to track whether its a folder or file
    is_root = models.BooleanField(default=True)  #used to track whether the Folder is a root folder or a sub folder
    parentFolder = models.ForeignKey("self" , on_delete=models.CASCADE, null=True , blank=True) #if the data is in the root structure , we dont have a parent folder other wise store the id of the parent

    #if the data is a file we need all this data
    file_url = models.URLField(null=True , blank=True) #if it's file we need the url of the data
    file_extension = models.TextField(null=True , blank=True) #if it's file we need the extension of the data
    upload_status = models.CharField(max_length=50 , null=True , choices=STATUS_CHOICES , default='PENDING')
    celery_task_ID = models.TextField(null=True , blank=True)

    #tracking if the file/folder states ....
    is_trash = models.BooleanField(default=False)
    is_favorite = models.BooleanField(default=False)


    def __str__(self) -> str:
        return self.name


    class Meta:
        verbose_name_plural = "FileFolderModels"


#DataBase model to track the storage of each user  (Will be used in future for tracking the storage limits of each user based on their tier) (also will conduct Audit in a periodic manner to update the used storage of each user to verify if the record details are correct)
class ClerkUserStorage(models.Model):
    author = models.ForeignKey(ClerkUserProfile, on_delete=models.CASCADE, related_name="storage_stats")
    clerk_user_storage_limit = models.BigIntegerField(null=False , default=0)
    clerk_user_used_storage = models.BigIntegerField(null=False ,  default=0)
    total_image_storage = models.BigIntegerField(null=False ,  default=0)
    total_document_storage = models.BigIntegerField(null=False ,  default=0)
    total_other_storage = models.BigIntegerField(null=False ,  default=0)
    storage_percentage_used = models.FloatField(null=False , default=0.0)

    def __str__(self):
        return f"Storage Stats of {self.author.clerk_user_name}"

