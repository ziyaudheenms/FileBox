from django.contrib import admin
from .models import ClerkUserProfile, FileFolderModel, ClerkUserStorage, FileFolderPermission , ShareLink
# Register your models here.

admin.site.register(ClerkUserProfile)
admin.site.register(FileFolderModel)
admin.site.register(ClerkUserStorage)
admin.site.register(FileFolderPermission)
admin.site.register(ShareLink)