from rest_framework.views import exception_handler
from rest_framework.response import Response
from django.http import Http404  # <--- Add this import

def file_box_exception_handler(exc, context):
    # 1. Ask DRF to handle the error first
    response = exception_handler(exc, context)

    # 2. If DRF returned None, it's likely a standard Django Http404
    if response is None and isinstance(exc, Http404):
        return Response({
            "status_code": 5002,
            "message": "FileFolder Instance Not Found.",
            "data": ""
        }, status=404)

    # 3. If DRF did return a response but it's a 404, format the data
    if response is not None and response.status_code == 404:
        response.data = {
            "status_code": 5002,
            "message": "FileFolder Instance Not Found.",
            "data": ""
        }
    
    return response