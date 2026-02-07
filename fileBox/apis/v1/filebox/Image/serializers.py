from rest_framework import serializers
from Backend.models import FileFolderModel , ClerkUserStorage


class FileFolderSerializer(serializers.ModelSerializer):
    
    author = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    parentFolder = serializers.SerializerMethodField()

    class Meta:
        model = FileFolderModel
        fields = '__all__'

    def get_author(self, instance):
        return instance.author.clerk_user_name
    
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
        return round(calculation, 2)