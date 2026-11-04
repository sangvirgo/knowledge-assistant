from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import HttpResponse
from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token

from apps.chat import pages

urlpatterns = [
    path("", pages.chat_page, name="chat"),
    path("documents/", pages.documents_page, name="documents"),
    path("admin/", admin.site.urls),
    path("healthz", lambda request: HttpResponse("ok")),
    path("api/token/", obtain_auth_token),  # token cho API / MCP
    path("login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    path("api/", include("apps.documents.urls")),
    path("api/", include("apps.chat.urls")),
    path("api/", include("apps.agent.urls")),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
