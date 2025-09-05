"""
URL configuration for sist_rec_api project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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
from django.urls import path, include
from usuarios_log.views import RegisterView, LoginView
from rest_framework_simplejwt.views import TokenRefreshView
from usuarios_log.views import UserListView
from usuarios_log.views import UserUpdateView
from django.http import JsonResponse

def health(_): return JsonResponse({"ok": True})
urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/auth/register/", RegisterView.as_view()),
    path("api/auth/login/",    LoginView.as_view()),
    path("api/auth/refresh/",  TokenRefreshView.as_view()),
    path("api/auth/users/",    UserListView.as_view()),
    path("api/auth/users/<int:pk>/", UserUpdateView.as_view()),  # PATCH uno
    path("api/", include("recibos.urls")),
    path("api/", include("transferencias.urls")),
    path("health/", health),
]
