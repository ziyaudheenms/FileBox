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
    clerk_user_available_storage_gb = models.BigIntegerField(null=False)
    clerk_user_used_storage_gb = models.BigIntegerField(null=False)
    clerk_user_created_at = models.DateTimeField(auto_now_add=True)
    clerk_user_updated_at = models.DateTimeField(auto_now=True)
    clerk_user_tier = models.CharField(max_length=50 , null=False , choices=TIER_OPTIONS , default='FREE')

    def __str__(self) -> str:
        return self.clerk_user_name
    


class FolderModel(models.Model):
    author = models.ForeignKey(ClerkUserProfile,on_delete=models.CASCADE , related_name="folder")
    name = models.CharField(max_length=255, blank=False, null=False)
    is_root_folder = models.BooleanField(default=True)  #used to track whether the Folder is a root folder or a sub folder
    parentID = models.ForeignKey("self" , on_delete=models.CASCADE , related_name="parent" , null=True , blank=True) # used to store the ID of the parent folder , if exists
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    no_of_items = models.IntegerField(default=0)


class FileModel(models.Model):

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('UPLOADED', 'Uploaded'),
        ('FAILED', 'Failed'),
    ]

    author = models.ForeignKey(ClerkUserProfile , on_delete=models.CASCADE , related_name='files')
    file_url = models.URLField(null=False)
    file_name = models.TextField(null=False)
    file_size = models.FloatField(null=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    file_extension = models.TextField(null=False)
    upload_status = models.CharField(max_length=50 , null=False , choices=STATUS_CHOICES , default='PENDING')
    celery_task_ID = models.TextField(null=False , blank=False)
    parentFolder = models.ForeignKey(FolderModel , on_delete=models.CASCADE, related_name="folder_name" , null=True , blank=True)

    def __str__(self) -> str:
        return self.file_name





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
    size = models.FloatField(null=True) #if the data record is folder , we will dynsmicslly set the size in the  serializer.
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
      



