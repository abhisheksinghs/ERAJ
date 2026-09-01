from django.contrib import admin
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.core.models import (
    AuditLog,
    Client,
    Domain,
    Module,
    Plan,
    PlanModule,
    Subscription,
)
from config.admin import admin_site

for _model in (Client, Domain, Plan, Module, PlanModule, Subscription, TOTPDevice, StaticDevice):
    admin_site.register(_model)


@admin.register(AuditLog, site=admin_site)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("at", "schema_name", "action", "actor")
    list_filter = ("action", "schema_name")
    search_fields = ("actor", "action")
    readonly_fields = ("at", "schema_name", "actor", "action", "detail")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
