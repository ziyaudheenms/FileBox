from django.contrib import admin
from .models import ClerkUserProfile , FileModel , FileFolderModel
# Register your models here.

admin.site.register(ClerkUserProfile)
admin.site.register(FileModel)
admin.site.register(FileFolderModel)