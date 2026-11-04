from django.contrib import admin

from .models import PendingAction, Ticket

admin.site.register(Ticket)
admin.site.register(PendingAction)
