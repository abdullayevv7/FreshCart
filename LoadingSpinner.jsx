"""
Custom pagination classes for FreshCart REST API.

Provides consistent pagination across all endpoints with
configurable page size and metadata in the response.
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsSetPagination(PageNumberPagination):
    """
    Standard paginator used across the platform.

    Returns page metadata including total count, page size,
    and navigation links.

    Query params:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            "count": self.page.paginator.count,
            "page": self.page.number,
            "page_size": self.get_page_size(self.request),
            "total_pages": self.page.paginator.num_pages,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "results": data,
        })

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Total number of results.",
                },
                "page": {
                    "type": "integer",
                    "description": "Current page number.",
                },
                "page_size": {
                    "type": "integer",
                    "description": "Number of results per page.",
                },
                "total_pages": {
                    "type": "integer",
                    "description": "Total number of pages.",
                },
                "next": {
                    "type": "string",
                    "nullable": True,
                    "format": "uri",
                    "description": "URL for the next page of results.",
                },
                "previous": {
                    "type": "string",
                    "nullable": True,
                    "format": "uri",
                    "description": "URL for the previous page of results.",
                },
                "results": schema,
            },
        }


class LargeResultsSetPagination(PageNumberPagination):
    """
    Pagination for endpoints that typically return more results,
    such as product listings or order history.
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data):
        return Response({
            "count": self.page.paginator.count,
            "page": self.page.number,
            "page_size": self.get_page_size(self.request),
            "total_pages": self.page.paginator.num_pages,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "results": data,
        })


class SmallResultsSetPagination(PageNumberPagination):
    """
    Pagination for endpoints with smaller result sets,
    such as reviews or addresses.
    """

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50

    def get_paginated_response(self, data):
        return Response({
            "count": self.page.paginator.count,
            "page": self.page.number,
            "page_size": self.get_page_size(self.request),
            "total_pages": self.page.paginator.num_pages,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "results": data,
        })
