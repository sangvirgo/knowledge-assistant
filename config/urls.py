from django.contrib import admin
from django.http import HttpResponse
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", lambda request: HttpResponse("ok")),
]
