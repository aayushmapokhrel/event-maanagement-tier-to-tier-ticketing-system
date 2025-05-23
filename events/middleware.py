from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages


class AdminAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/custom-admin/"):
            if not request.user.is_authenticated:
                messages.error(request, "Please log in to access the admin dashboard.")
                return redirect(reverse("login") + f"?next={request.path}")

            if not request.user.is_staff:
                messages.error(
                    request, "You do not have permission to access the admin dashboard."
                )
                return redirect("home")

        response = self.get_response(request)
        return response
