from os import read

from attr import field
from rest_framework import serializers
from Backend.models import FileFolderModel , ClerkUserStorage , ClerkUserProfile, ShareLink
from ..hashDependency import hash_ID
from ..SignedURL import iamgekit_signed_URL
from django.contrib.humanize.templatetags.humanize import naturaltime



class FileFolderSerializer(serializers.ModelSerializer):
    
    author = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    parentFolder = serializers.SerializerMethodField()
    pathnames = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()

    class Meta:
        model = FileFolderModel
        fields = '__all__'

    def get_author(self, instance):
        return instance.author.clerk_user_name
    def get_profile_image(self, instance):
        return instance.author.clerk_user_profile_img
    
    def get_size(self, instance):
        if instance.isfolder:
            total_instance = FileFolderModel.objects.filter(parentFolder=instance , is_trash=False)
            total_size = sum([file.size for file in total_instance])
            return total_size if total_size else 0
        else:
            return instance.size
        
    def get_parentFolder(self, instance):
        if instance.is_root:
            return None
        else:
            return instance.parentFolder.name
    
    def get_pathnames(self, instance):
        ids =  instance.path.split('/') if instance.path else []
        folderNames = FileFolderModel.objects.filter(pk__in =ids).values_list('name', flat=True)
        return '/'.join(folderNames)
    
    def get_file_url(self,instance):
        if instance.file_url is None:
            return None
        return iamgekit_signed_URL.generate_signed_url(instance.file_url)

class UserStorageSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    clerk_user_storage_limit = serializers.SerializerMethodField()
    clerk_user_used_storage = serializers.SerializerMethodField()
    total_image_storage = serializers.SerializerMethodField()
    total_document_storage = serializers.SerializerMethodField()
    total_other_storage = serializers.SerializerMethodField()
    storage_percentage_used = serializers.SerializerMethodField()

    class Meta:
        model = ClerkUserStorage
        fields = '__all__'

    def get_author(self, instance):
        return instance.author.clerk_user_name
    
    def get_clerk_user_storage_limit(self, instance):
        gb_typecated_value = instance.clerk_user_storage_limit / (1024 * 1024)
        print(instance.clerk_user_storage_limit , "storage limit")
        print(gb_typecated_value)
        print(round(gb_typecated_value, 2))
        return f"{round(gb_typecated_value, 2)} GB"
    
    def get_clerk_user_used_storage(self, instance):
        if instance.clerk_user_used_storage < 1024:
            return f"{instance.clerk_user_used_storage} KB"
        elif instance.clerk_user_used_storage < (1024 * 1024):
            mg_typecasted_value = instance.clerk_user_used_storage / 1024
            return f"{round(mg_typecasted_value, 2)} MB"
        else:
            gb_typecasted_value = instance.clerk_user_used_storage / (1024 * 1024)
            return f"{round(gb_typecasted_value, 2)} GB"
        
    def get_total_image_storage(self, instance):
        if instance.total_image_storage < 1024:
            return f"{instance.total_image_storage} KB"
        elif instance.total_image_storage < (1024 * 1024):
            mg_typecasted_value = instance.total_image_storage / 1024
            return f"{round(mg_typecasted_value, 2)} MB"
        else:
            gb_typecasted_value = instance.total_image_storage / (1024 * 1024)
            return f"{round(gb_typecasted_value, 2)} GB"
        
    def get_total_document_storage(self, instance):
        if instance.total_document_storage < 1024:
            return f"{instance.total_document_storage} KB"
        elif instance.total_document_storage < (1024 * 1024):
            mg_typecasted_value = instance.total_document_storage / 1024
            return f"{round(mg_typecasted_value, 2)} MB"
        else:
            gb_typecasted_value = instance.total_document_storage / (1024 * 1024)
            return f"{round(gb_typecasted_value, 2)} GB"
        
    def get_total_other_storage(self, instance):
        if instance.total_other_storage < 1024:
            return f"{instance.total_other_storage} KB"
        elif instance.total_other_storage < (1024 * 1024):
            mg_typecasted_value = instance.total_other_storage / 1024
            return f"{round(mg_typecasted_value, 2)} MB"
        else:
            gb_typecasted_value = instance.total_other_storage / (1024 * 1024)
            return f"{round(gb_typecasted_value, 2)} GB"    
    
    def get_storage_percentage_used(self, instance):
        calculation = (instance.clerk_user_used_storage / instance.clerk_user_storage_limit ) * 100
        print(calculation)
        print(round(calculation, 2))
        return round(calculation, 2)    
    

class PermissionUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClerkUserProfile
        fields = [ 'clerk_user_name' , 'clerk_user_email' , 'clerk_user_profile_img' , "pk"]


class FileFolderShareSerializer(serializers.ModelSerializer):
    
    author = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    parentFolder = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

  

    class Meta:
        model = FileFolderModel
        exclude = ['celery_task_ID', 'upload_status','is_favorite','is_trash']

    def get_author(self, instance):
        return instance.author.clerk_user_name
    
    def get_profile_image(self, instance):
        return instance.author.clerk_user_profile_img
    
    def get_size(self, instance):
        if instance.isfolder:
            total_instance = FileFolderModel.objects.filter(parentFolder=instance , is_trash=False)
            total_size = sum([file.size for file in total_instance])
            return total_size if total_size else 0
        else:
            return instance.size
        
    def get_parentFolder(self, instance):
        if instance.is_root:
            return None
        else:
            return instance.parentFolder.name
        
    def get_file_url(self,instance):
        if instance.file_url is None:
            return None
        return iamgekit_signed_URL.generate_signed_url(instance.file_url)


class ChildFileFolderShareSerializer(serializers.ModelSerializer):
    
    author = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    parentFolder = serializers.SerializerMethodField()
    id = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()

  

    class Meta:
        model = FileFolderModel
        exclude = ['celery_task_ID', 'upload_status','is_favorite','is_trash','path']

    def get_author(self, instance):
        return instance.author.clerk_user_name
    
    def get_profile_image(self, instance):
        return instance.author.clerk_user_profile_img

    def get_size(self, instance):
        if instance.isfolder:
            total_instance = FileFolderModel.objects.filter(parentFolder=instance , is_trash=False)
            total_size = sum([file.size for file in total_instance])
            return total_size if total_size else 0
        else:
            return instance.size
        
    def get_parentFolder(self, instance):
        if instance.is_root:
            return None
        else:
            return instance.parentFolder.name
    def get_id(self, instance):
        encoded_id = hash_ID.encode_id(instance.pk)
        if encoded_id is  None:
            return instance.pk
        return encoded_id
    def get_file_url(self,instance):
        if instance.file_url is None:
            return None
        return iamgekit_signed_URL.generate_signed_url(instance.file_url)
    



class ShareChildFileFolderShareSerializer(serializers.ModelSerializer):
    
    id = serializers.SerializerMethodField()
    updated_at = serializers.SerializerMethodField()
    
    class Meta:
        model = FileFolderModel
        fields = ['name', 'type_of_file_folder','updated_at',  'id']
        
    def get_id(self, instance):
        encoded_id = hash_ID.encode_id(instance.pk)
        if encoded_id is  None:
            return instance.pk
        return encoded_id
    
    def get_updated_at(self, instance):
        return naturaltime(instance.updated_at)
    


class SearchResultSerializer(serializers.ModelSerializer):
    #defining the columns that actually is not present in the DB , but created by annotate
    rank = serializers.FloatField(read_only=True)
    snippet = serializers.CharField(read_only=True)

    class Meta:
        model = FileFolderModel
        fields = ["id" , "author" , "name" , "type_of_file_folder" , "rank" , "snippet" , "description" , "isfolder"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # if relevance and snippet are none , just remove them
        if data.get('rank') is None:
            data.pop('rank', None)
            data.pop('snippet', None)
            
        return data