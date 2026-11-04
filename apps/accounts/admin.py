from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Department, User

admin.site.register(Department)


@admin.register(User)
class AppUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Tổ chức", {"fields": ("department", "role")}),)
    list_display = ("username", "department", "role", "is_staff")
