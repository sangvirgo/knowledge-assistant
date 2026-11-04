from django.urls import path

from . import views

urlpatterns = [
    path("agent/ask", views.AgentAskView.as_view()),
    path("actions/<int:pk>/approve", views.ActionDecisionView.as_view(approve=True)),
    path("actions/<int:pk>/reject", views.ActionDecisionView.as_view(approve=False)),
]
