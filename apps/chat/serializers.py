from rest_framework import serializers

from .models import ChatSession, Message


class AskSerializer(serializers.Serializer):
    session_id = serializers.IntegerField(required=False)
    question = serializers.CharField(max_length=4000)


class SessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = ["id", "title", "created_at"]


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["id", "role", "content", "sources", "trace_id", "created_at"]
