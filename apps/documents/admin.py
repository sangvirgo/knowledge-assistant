from django.contrib import admin

from .models import Chunk, Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "department", "visibility", "status", "created_at")
    list_filter = ("status", "visibility", "department")


admin.site.register(Chunk)
