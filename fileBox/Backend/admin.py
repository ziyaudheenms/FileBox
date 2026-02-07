from django.contrib import admin
from .models import ClerkUserProfile  , FileFolderModel , ClerkUserStorage
# Register your models here.

admin.site.register(ClerkUserProfile)
admin.site.register(FileFolderModel)
admin.site.register(ClerkUserStorage)