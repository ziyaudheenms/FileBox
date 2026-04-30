from django.contrib import admin
from .models import ClerkUserProfile, FileFolderModel, ClerkUserStorage, FileFolderPermission , ShareLink , ResourceSecurityPolicies , SecuritySession
# Register your models here.

admin.site.register(ClerkUserProfile)
admin.site.register(FileFolderModel)
admin.site.register(ClerkUserStorage)
admin.site.register(FileFolderPermission)
admin.site.register(ShareLink)
admin.site.register(ResourceSecurityPolicies)
admin.site.register(SecuritySession)