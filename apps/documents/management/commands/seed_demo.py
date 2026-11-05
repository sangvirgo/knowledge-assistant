"""Tạo dữ liệu demo: phòng ban, người dùng, và nạp các tài liệu mẫu trong samples/.

Chạy:  python manage.py seed_demo        (idempotent: chạy lại không tạo trùng)
"""

from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token

from apps.accounts.models import Department, User
from apps.documents.models import Document
from apps.documents.services.ingest import ingest

SAMPLES = Path(settings.BASE_DIR) / "samples"
USERS = {  # username: (department, role)
    "alice": ("HR", "member"),
    "bob": ("Eng", "member"),
    "admin_demo": (None, "admin"),
}
PASSWORD = "demo1234"
ACL = {  # file stem: (department, visibility)
    "nghi-phep": ("HR", "company"),
    "an-toan-thong-tin": ("HR", "company"),
    "quy-tac-ung-xu": ("HR", "company"),
    "luong-thuong": ("HR", "department"),
    "tuyen-dung": ("HR", "department"),
    "deploy": ("Eng", "department"),
    "oncall": ("Eng", "department"),
    "coding-standards": ("Eng", "department"),
}


class Command(BaseCommand):
    help = "Seed demo departments, users and sample documents."

    def handle(self, *args, **opts):
        depts = {n: Department.objects.get_or_create(name=n)[0] for n in ("HR", "Eng")}
        users = {}
        for name, (dept, role) in USERS.items():
            u, created = User.objects.get_or_create(
                username=name, defaults={"department": depts.get(dept), "role": role}
            )
            if created:
                u.set_password(PASSWORD)
                u.is_staff = role == "admin"
                u.is_superuser = role == "admin"
                u.save()
            users[name] = u
        for stem, (dept, vis) in ACL.items():
            if Document.objects.filter(title=stem).exists():
                continue
            owner = users["alice" if dept == "HR" else "bob"]
            doc = Document.objects.create(
                title=stem, owner=owner, department=depts[dept], visibility=vis
            )
            doc.file.save(f"{stem}.md", ContentFile((SAMPLES / f"{stem}.md").read_bytes()))
            ingest(doc.pk)  # đồng bộ: demo không cần worker
            doc.refresh_from_db()
            self.stdout.write(f"  {stem:20} {vis:10} {dept:4} -> {doc.status}")
        self.stdout.write(self.style.SUCCESS(f"Demo accounts (password: {PASSWORD}):"))
        for name, (dept, role) in USERS.items():
            tok = Token.objects.get_or_create(user=users[name])[0].key
            self.stdout.write(f"  {name:11} dept={dept} role={role} token={tok}")
