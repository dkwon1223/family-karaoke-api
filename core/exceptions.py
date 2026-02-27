from rest_framework.views import exception_handler
from rest_framework.response import Response


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        error_message = response.data.get("detail", str(exc))
        response.data = {
            "error": str(error_message),
            "detail": response.data if not isinstance(response.data, str) else None,
        }

    return response