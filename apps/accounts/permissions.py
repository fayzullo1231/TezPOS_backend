from rest_framework.permissions import BasePermission


class IsTenantAdmin(BasePermission):
    """Tenant super_admin yoki admin."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.role in ("super_admin", "admin") or user.is_superuser
