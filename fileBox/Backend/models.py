from typing import Any
import uuid

from django.db import models
from django.utils import timezone
# Create your models here.


from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex
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
    type_of_file_folder = models.CharField(max_length=100 , null=True , blank=True) #used to track the type of the file (image , document , other) if it's a file and will be null if it's a folder
    size = models.BigIntegerField(null=False , default=0) #if the data record is folder , we will dynamically set the size in the  serializer.
    description = models.TextField(null=True , blank=True , default="") #if we need we can add desciptions..
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    isfolder = models.BooleanField(default=False) # Used to track whether its a folder or file
    is_root = models.BooleanField(default=True)  #used to track whether the Folder is a root folder or a sub folder
    parentFolder = models.ForeignKey("self" , on_delete=models.CASCADE, null=True , blank=True) #if the data is in the root structure , we dont have a parent folder other wise store the id of the parent
    path = models.TextField(null=True, blank=True, default=None , db_index=True) #used to track the parent structure  (will be null if is_root is True)


    #if the data is a file we need all this data
    file_url = models.URLField(null=True , blank=True) #if it's file we need the url of the data
    file_extension = models.TextField(null=True , blank=True) #if it's file we need the extension of the data
    upload_status = models.CharField(max_length=50 , null=True , choices=STATUS_CHOICES , default='PENDING')
    celery_task_ID = models.TextField(null=True , blank=True)
    imageKit_file_id = models.TextField(null=True , blank=True) #used to store the file id returned by imagekit after uploading the image which will be used in future for deleting the image from imagekit when the user deletes the file from filebox or when the user reuploads the file to update the file in imagekit because imagekit does not provide any update API for updating the existing file so we have to delete the existing file and upload the new file to update the file in imagekit.
    #tracking if the file/folder states ....
    is_trash = models.BooleanField(default=False)
    is_favorite = models.BooleanField(default=False)
    
    search_vector = SearchVectorField(null=True)

    def __str__(self) -> str:
        return self.name


    class Meta:
        verbose_name_plural = "FileFolderModels"
        indexes = [
            GinIndex(fields=['search_vector'] , name='file_search_vector_idx')
        ]



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

    class Meta:
        # This creates a Composite Unique Index in SQL (ensures that a user cannot have multiple permissions for the same file/folder instance)
        unique_together = ('fileFolder_Instance_id', 'user_id')

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

class ResourceSecurityPolicies(models.Model):
    file_folder_instance = models.OneToOneField(FileFolderModel, on_delete=models.CASCADE, related_name="security_policies")
    encypted_password = models.TextField(null=True, blank=True) #used to store the encrypted password for the fileFolder instance (PREMIUM FEATURE)
    is_critical = models.BooleanField(default=False) #used to track the critical files/folders of the user 
    is_password_protected = models.BooleanField(default=False) #used to track whether the file/folder is password protected or not
    is_locked = models.BooleanField(default=False) # if yes , each time the resource is clicked, user is prompted to enter the password.
    session_duration = models.IntegerField(default=1) #used to set the time interval for opening the file since the password is given. (duration is given in minutes.)
    def __str__(self):
        return f"Security Policies for {self.file_folder_instance.name}"


class SecuritySession(models.Model):
    session_user = models.ForeignKey(ClerkUserProfile, on_delete=models.CASCADE, related_name="security_user_session")
    file_folder_instance = models.ForeignKey(FileFolderModel, on_delete=models.CASCADE, related_name="security_session_file_folder_instance")
    session_token = models.TextField(null=False) #used to store the session token for the fileFolder instance (PREMIUM FEATURE) -> encrypted unique string 
    created_at_or_updated_at = models.DateTimeField(auto_now_add=True)
    expiry_time = models.DateTimeField()

    def __str__(self):
        return f"Security Session for {self.file_folder_instance.name} - {self.created_at_or_updated_at}"
    