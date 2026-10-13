"""
Accounts: log in, sign up and log out with a username and password.

    /login/    custom login page (Django's LoginView with our template)
    /signup/   create an account, then sign straight in
    /logout/   POST only: signs out and returns to the home page
"""

from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, resolve_url
from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import CreateView

from .forms import SignUpForm
from .models import Traveler


class TakeOffLoginView(LoginView):
    """Login form. A visitor who is already signed in is sent on instead of seeing the form again."""

    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class SignUpView(CreateView):
    """Create an account and its travel profile, sign the new user in, then continue to ?next= or home."""

    form_class = SignUpForm
    template_name = "accounts/signup.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(settings.LOGIN_REDIRECT_URL)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        Traveler.for_user(user)  # every account gets its travel profile straight away
        login(self.request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect(self.get_success_url())

    def get_success_url(self):
        # Honour ?next= (the page that asked for a login) but only if it points at this site.
        next_url = self.request.POST.get("next") or self.request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={self.request.get_host()}, require_https=self.request.is_secure()
        ):
            return next_url
        return resolve_url(settings.LOGIN_REDIRECT_URL)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["next"] = self.request.GET.get("next", "")
        return ctx
