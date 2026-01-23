from rest_framework import serializers
from Backend.models import FileFolderModel


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
            total_size = FileFolderModel.objects.filter(parentFolder=instance , is_trash=False).count()
            return total_size if total_size else 0
        else:
            return instance.size
        
    def get_parentFolder(self, instance):
        if instance.is_root:
            return None
        else:
            return instance.parentFolder.name