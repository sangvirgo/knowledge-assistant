from django.contrib.auth.models import AbstractUser
from django.db import models


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    class Role(models.TextChoices):
        MEMBER = "member"
        ADMIN = "admin"

    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="users"
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)

    @property
    def is_company_admin(self) -> bool:
        return self.role == self.Role.ADMIN
