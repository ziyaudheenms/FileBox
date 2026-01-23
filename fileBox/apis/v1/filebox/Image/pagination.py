from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
# Custom Pagination Class For FileFolder GET API Responce.
class FileFolderCursorBasedPagination(CursorPagination):
    page_size = 12
    ordering = "-uploaded_at"
    cursor_query_param = "cursor"

    # Customizing the paginated response format by including additional metadata.
    def get_paginated_response(self, data):
        return Response({
            "status_code" : 5000,
            "message" : {
                "next_cursor": self.get_next_link(),
                "previous_cursor": self.get_previous_link(),
            },
            "data" : data,
            
        })