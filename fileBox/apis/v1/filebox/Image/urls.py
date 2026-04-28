from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('Create/Image/', views.uploadImage), #used to upload the image
    path('Create/Folder/', views.createFolder), #api endpoint to create the folder
    path('delete/FolderFile/', views.delete_filefolderRecord), # api endpoint for deleteing the folder or file (pk id is sent through params)
    path('trash/FolderFile/', views.isTrash), #api endpoint for updating whether the file/folder is in trash or not
    path('favorite/FolderFile/', views.isFavorite), #api endpoint for updating whether the file/folder is in favorite or not
    path('test/' , views.testFunction),
    path('Create/Image/Chunk/' , views.ChunkImage),
    path('Create/Image/Chunk/Join/' , views.JoinChunks),
    path('fileFolders', views.getAllFileFolders), #api endpoint to get all the files/folders + file/folder pagination along with if it's inside any saperate folder using params.
    path('fileFolders/Trash', views.getTrashFileFolders), #api endpoint to get all the trashed files/folders + file/folder pagination along with if it's inside any saperate folder using params.
    path('fileFolders/Favorite', views.getFavoriteFileFolders), #api endpoint to get all the favorite files/folders + file/folder pagination along with if it's inside any saperate folder using params.
    path('fileFolders/Image', views.getSingleImage), #api endpoint to get single image details using pk id sent through params
    path('storage/status/' , views.getStorageDetails), # this api endpoint is used to get the storage details of the user
    path('permission/getUser' , views.get_the_user_for_permission),
    path('permission/grandUsers' , views.assign_permission_to_user),
    path('permission/Users' , views.get_User_With_Permission),
    path('get/sharableLink' , views.generate_share_link),
    path('get/sharedFileFolder' , views.access_shared_file_folder),
    path('get/sharedFileFolder/child' , views.access_child_of_shared_folder),
    path('move/availableRecords' , views.list_the_possible_folders_to_move),
    path('move/' , views.move_file_folder),
    path('copy/' , views.copy_file_folder),
    path('update/file/' , views.update_file_meta_data),
    path('search/' , views.search_file_folders),
    path('verify/password' , views.check_password_return_session_token),
    path('security/policy' , views.create_or_update_security_policy),
]
                            