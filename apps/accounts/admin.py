from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Shift, Tenant, User


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ["server_name", "display_name", "is_active", "created_at"]
    search_fields = ["server_name", "display_name"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "tenant", "role", "is_active"]
    list_filter = ["role", "tenant", "is_active"]
    fieldsets = BaseUserAdmin.fieldsets + (
        ("TezPOS", {"fields": ("tenant", "role", "api_token", "phone")}),
    )
    readonly_fields = ["api_token"]


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ["user", "tenant", "status", "opened_at", "closed_at"]
