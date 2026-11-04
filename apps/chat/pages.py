from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie


@login_required
@ensure_csrf_cookie  # JS đọc cookie csrftoken để gọi API bằng session
def chat_page(request):
    return render(request, "chat.html")


@login_required
@ensure_csrf_cookie
def documents_page(request):
    return render(request, "documents.html")
