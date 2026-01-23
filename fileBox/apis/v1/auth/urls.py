from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('createUser/', views.create_clerk_user),
    path('updateUser/', views.update_clerk_user),
]
