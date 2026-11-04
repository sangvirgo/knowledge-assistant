from django.conf import settings
from django.db import models


class Ticket(models.Model):
    """Ticket mô phỏng (chỉ lưu DB) — hành động có tác dụng phụ của agent."""

    title = models.CharField(max_length=255)
    body = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    session = models.ForeignKey("chat.ChatSession", null=True, on_delete=models.SET_NULL)
    tool_call_id = models.CharField(max_length=100, blank=True)  # chống tạo trùng khi resume
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "tool_call_id"],
                condition=~models.Q(tool_call_id=""),
                name="uniq_ticket_call",
            )
        ]


class PendingAction(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"

    session = models.ForeignKey("chat.ChatSession", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tool = models.CharField(max_length=50)
    args = models.JSONField(default=dict)
    tool_call_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
