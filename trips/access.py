"""
Access control shared by the JSON API.

Pages use Django's own @login_required / LoginRequiredMixin, which redirect a visitor who is not
signed in to the login page. A script or chart reading an API cannot follow a login page, so
protected APIs answer with a 401 JSON error instead of an HTML redirect.
"""

from functools import wraps

from django.http import JsonResponse
from django.shortcuts import resolve_url
from django.conf import settings


def api_login_required(view_func):
    """Allow the API call only for a signed-in user; otherwise answer 401 with a JSON error."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {
                    "error": "Authentication required. Log in to use this API.",
                    "login_url": resolve_url(settings.LOGIN_URL),
                },
                status=401,
            )
        return view_func(request, *args, **kwargs)

    return wrapper
