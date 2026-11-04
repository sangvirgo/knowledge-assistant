from django.urls import path

from . import views

urlpatterns = [
    path("ask", views.AskView.as_view()),
    path("sessions/", views.SessionListView.as_view()),
    path("sessions/<int:pk>/messages/", views.SessionMessagesView.as_view()),
]
