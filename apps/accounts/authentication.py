from rest_framework import authentication, exceptions

from .models import Tenant, User


class TenantTokenAuthentication(authentication.BaseAuthentication):
    """
    Har bir so'rov: X-Server-Name + Authorization: Token <api_token>
  yoki login sessiyasi.
    """

    keyword = "Token"

    def authenticate(self, request):
        server_name = request.headers.get("X-Server-Name", "").strip()
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith(f"{self.keyword} "):
            return None

        token = auth_header[len(self.keyword) + 1 :].strip()
        if not token:
            return None

        try:
            if server_name:
                tenant = Tenant.objects.get(server_name__iexact=server_name, is_active=True)
                user = User.objects.select_related("tenant").get(
                    api_token=token, tenant=tenant, is_active=True
                )
            else:
                user = User.objects.select_related("tenant").get(
                    api_token=token, is_active=True
                )
        except (Tenant.DoesNotExist, User.DoesNotExist):
            raise exceptions.AuthenticationFailed("Noto'g'ri server yoki token.")

        if not user.tenant or not user.tenant.is_active:
            raise exceptions.AuthenticationFailed("Server faol emas.")

        request.tenant = user.tenant
        return (user, token)
