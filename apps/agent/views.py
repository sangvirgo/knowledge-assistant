import json

from django.db import transaction
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chat.models import ChatSession
from apps.chat.serializers import AskSerializer

from .models import PendingAction
from .services.runner import resolve_action, run_to_result, start_turn


def _sse(events):
    for e in events:
        yield f"event: {e['event']}\ndata: {json.dumps(e['data'], ensure_ascii=False)}\n\n"


def _stream_response(events):
    r = StreamingHttpResponse(_sse(events), content_type="text/event-stream")
    r["Cache-Control"] = "no-cache"
    r["X-Accel-Buffering"] = "no"
    return r


class AgentAskView(APIView):
    """`?stream=1` => SSE; ngược lại JSON."""

    def post(self, request):
        s = AskSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        sid = s.validated_data.get("session_id")
        if sid:
            get_object_or_404(ChatSession, pk=sid, user=request.user)
        events = start_turn(request.user, s.validated_data["question"], sid)
        if request.query_params.get("stream"):
            return _stream_response(events)
        return Response(run_to_result(events))


class ActionDecisionView(APIView):
    approve: bool = True

    def post(self, request, pk):
        with transaction.atomic():
            # khoá hàng để hai lần bấm không resume đồ thị hai lần
            action = get_object_or_404(
                PendingAction.objects.select_for_update(), pk=pk, user=request.user
            )
            if action.status != PendingAction.Status.PENDING:
                return Response({"detail": "Hành động đã được xử lý."}, status=409)
            events = resolve_action(request.user, action, self.approve)
            if request.query_params.get("stream"):
                return _stream_response(events)
            return Response(run_to_result(events))
