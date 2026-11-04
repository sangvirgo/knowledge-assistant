from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import ChatSession
from .serializers import AskSerializer, MessageSerializer, SessionSerializer
from .services.rag import ask


class AskView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ask"

    def post(self, request):
        s = AskSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        sid = s.validated_data.get("session_id")
        if sid:
            get_object_or_404(ChatSession, pk=sid, user=request.user)
        return Response(ask(request.user, s.validated_data["question"], sid))


class SessionListView(APIView):
    def get(self, request):
        qs = ChatSession.objects.filter(user=request.user).order_by("-id")
        return Response(SessionSerializer(qs, many=True).data)


class SessionMessagesView(APIView):
    def get(self, request, pk):
        session = get_object_or_404(ChatSession, pk=pk, user=request.user)
        return Response(MessageSerializer(session.messages.all(), many=True).data)
