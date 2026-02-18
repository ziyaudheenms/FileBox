from rest_framework.views import exception_handler
from rest_framework.response import Response

def file_box_exception_handler(exc, context):
    responce = exception_handler(exc, context)

    if responce is not None and responce.status_code == 404:
        responce.data = {
            "status_code": 5002,
            "message": "FileFolder Instance Not Found.",
            "data": ""
        }
    
    return responce