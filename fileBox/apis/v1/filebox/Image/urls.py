from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('Create/Image/', views.uploadImage), #used to upload the image
    path('Create/Folder/', views.createFolder), #api endpoint to create the folder
    path('delete/FolderFile/', views.deleteFolderFile), # api endpoint for deleteing the folder or file (pk id is sent through params)
    path('trash/FolderFile/', views.isTrash), #api endpoint for updating whether the file/folder is in trash or not
    path('favorite/FolderFile/', views.isFavorite), #api endpoint for updating whether the file/folder is in favorite or not
    path('test/' , views.testFunction),
    path('Create/Image/Chunk/' , views.ChunkImage),
    path('Create/Image/Chunk/Join/' , views.JoinChunks),
    path('fileFolders', views.getAllFileFolders), #api endpoint to get all the files/folders + file/folder pagination along with if it's inside any saperate folder using params.
    path('fileFolders/Trash', views.getTrashFileFolders), #api endpoint to get all the trashed files/folders + file/folder pagination along with if it's inside any saperate folder using params.
    path('fileFolders/Favorite', views.getFavoriteFileFolders), #api endpoint to get all the favorite files/folders + file/folder pagination along with if it's inside any saperate folder using params.
    path('fileFolders/Image', views.getSingleImage), #api endpoint to get single image details using pk id sent through params
    path('storage/status/' , views.getStorageDetails) # this api endpoint is used to get the storage details of the user
]
                            