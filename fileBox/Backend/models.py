from typing import Any
import uuid

from django.db import models
from django.utils import timezone
# Create your models here.


class ClerkUserProfile(models.Model):

    TIER_OPTIONS = [
        ('FREE', 'Free'),
        ('PRO', 'Pro'),
        ('ADVANCED', 'Advanced'),
        ]
    clerk_user_id = models.TextField(null=False , unique=True , db_index=True)  #used for fast fetching of the clerkID without the need of scanning the entire Database.
    clerk_user_name = models.TextField(null=False)
    clerk_user_email = models.EmailField(null=False , unique=True)
    clerk_user_created_at = models.DateTimeField(auto_now_add=True)
    clerk_user_updated_at = models.DateTimeField(auto_now=True)
    clerk_user_tier = models.CharField(max_length=50 , null=False , choices=TIER_OPTIONS , default='FREE')
    clerk_user_profile_img = models.TextField(default="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRFCzxivJXCZk0Kk8HsHujTO3Olx0ngytPrWw&s",)

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

#DataBase Model to handle the permissions of accessing , edititing of a fileFolder instance. (User's Access in a protected fileFolder)
class FileFolderPermission(models.Model):
    STATUS_CHOICES = [
        ('VIEW', 'View'), # can only view the fileFolder or instances like that.
        ('EDIT', 'Edit'), # can view + edit the fileFolder or instances like that. (remane , add description)
        ('ADMIN', 'Admin'), # can do anything as like the author of the fileFolder or instances like that. (remane , add description , delete , reupload)
    ]

    fileFolder_Instance_id = models.ForeignKey(FileFolderModel, on_delete=models.CASCADE, related_name="file_folder_permissions")
    user_id = models.ForeignKey(ClerkUserProfile, on_delete=models.CASCADE, related_name="user_to_be_granted_with_permission")
    permission_type = models.CharField(max_length=100 , choices=STATUS_CHOICES , default="VIEW")
    permission_granted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_id.clerk_user_name} - {self.permission_type} - {self.fileFolder_Instance_id.name}"

class ShareLink(models.Model):
    VIEW_CHOICES = [
        ('PUBLIC', 'Public'), # can only view the fileFolder or instances like that.
        ('PRIVATE', 'Private'), # can only view the fileFolder or instances like that. 
    ]
    TYPE_CHOICES = [
        ('FILE', 'File'), # can only view the fileFolder or instances like that.
        ('FOLDER', 'Folder'), # can only view the fileFolder or instances like that.   
    ]
    shareable_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True) #used to store the custom ID to be send with the url
    view_type = models.CharField(max_length=100 , choices=VIEW_CHOICES , default='PRIVATE') 
    file_folder_instance = models.ForeignKey(FileFolderModel, on_delete=models.CASCADE, related_name="file_folder")
    owner = models.ForeignKey(ClerkUserProfile, on_delete=models.CASCADE , related_name="share_owner")
    data_type = models.CharField(max_length=100 , choices=TYPE_CHOICES , default='FILE')
    is_active = models.BooleanField(default=True)

    #Premium Feature -> 
    expires_at = models.DateTimeField(null=True, blank=True)
    password_hash = models.TextField(null=True) #used to store the hashed password in case the fileFolder is a password protected one  (PREMIUM FEATURE)
    access_count = models.IntegerField(default=0) # How many time the fileFolder instace has been opened.
    max_count = models.IntegerField(null=True, blank=True) #used to set the no of times this fileFolder should be clicked.

    @property
    def is_expired(self):  #returns true if the sharable link is expired , 
        if self.expires_at and timezone.now() > self.expires_at:
            return True
        return False
    
    @property
    def count_limited(self):
        if self.max_count and self.access_count >= self.max_count:
            return True
        return False
    


    def __str__(self):
        return f"{self.shareable_id} - {self.view_type} - {self.owner.clerk_user_name}"
