"""
URL configuration for takeoff project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),

    # Our own login and signup pages are the only ones: allauth's copies redirect to them.
    path('accounts/login/', RedirectView.as_view(pattern_name='trips:login', query_string=True)),
    path('accounts/signup/', RedirectView.as_view(pattern_name='trips:signup', query_string=True)),
    # django-allauth: Google OAuth start (/accounts/google/login/) and callback
    # (/accounts/google/login/callback/).
    path('accounts/', include('allauth.urls')),

    path('', include('trips.urls')),   # trips app owns the site root
]
