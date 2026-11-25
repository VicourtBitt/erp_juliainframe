from django.conf import settings
from django.contrib.auth.views import redirect_to_login

# Paths reachable without being logged in.
PUBLIC_PREFIXES = ("/login/", "/admin/", "/static/")


class LoginRequiredMiddleware:
    """Require authentication for every page except the public prefixes.

    The Streamlit app had no authentication at all; financial data and
    contracts were open to anyone holding the URL.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        if not request.user.is_authenticated and not path.startswith(PUBLIC_PREFIXES):
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        return self.get_response(request)
