from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sales.models import Sale

from .models import Employee, Shift, Tenant, User
from .shift_utils import compute_shift_summary, suggested_opening_balances
from .permissions import IsTenantAdmin
from .serializers import (
    EmployeeSerializer,
    LoginSerializer,
    RegisterSerializer,
    ShiftOpenSerializer,
    ShiftSerializer,
    StaffCreateSerializer,
    StaffUpdateSerializer,
    StaffUserSerializer,
    TenantCreateSerializer,
    TenantInfoSerializer,
    UserSerializer,
)


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok", "service": "TezPOS API"})


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        request.tenant = serializer.validated_data["tenant"]
        return Response(
            {
                "user": UserSerializer(user).data,
                "token": user.api_token,
                "server_name": user.tenant.server_name,
            }
        )


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "user": UserSerializer(user).data,
                "token": user.api_token,
                "server_name": user.tenant.server_name,
            },
            status=status.HTTP_201_CREATED,
        )


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class TenantStaffListView(APIView):
    """Tenant foydalanuvchilari (login hisoblari)."""

    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        tenant = request.user.tenant
        if not tenant:
            return Response({"results": []})
        users = User.objects.filter(tenant=tenant).order_by(
            "first_name", "last_name", "username"
        )
        return Response({"results": StaffUserSerializer(users, many=True).data})

    def post(self, request):
        serializer = StaffCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(StaffUserSerializer(user).data, status=status.HTTP_201_CREATED)


class TenantStaffDetailView(APIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def patch(self, request, user_id):
        tenant = request.user.tenant
        user = User.objects.filter(tenant=tenant, id=user_id).first()
        if not user:
            return Response({"detail": "Foydalanuvchi topilmadi."}, status=status.HTTP_404_NOT_FOUND)
        if user.id == request.user.id and request.data.get("is_active") is False:
            return Response(
                {"detail": "O'zingizni o'chirib bo'lmaydi."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = StaffUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(StaffUserSerializer(user).data)


class TenantInfoView(APIView):
    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        tenant = request.user.tenant
        if not tenant:
            return Response({"detail": "Server topilmadi."}, status=status.HTTP_404_NOT_FOUND)
        return Response(TenantInfoSerializer(tenant).data)


class TenantCreateView(APIView):
    """Yangi do'kon (server) yaratish — platforma yoki ro'yxatdan o'tish."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TenantCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant = serializer.save()
        admin = User.objects.filter(tenant=tenant, role="super_admin").first()
        return Response(
            {
                "tenant": TenantInfoSerializer(tenant).data,
                "user": UserSerializer(admin).data if admin else None,
                "token": admin.api_token if admin else None,
                "server_name": tenant.server_name,
            },
            status=status.HTTP_201_CREATED,
        )


class EmployeeListCreateView(APIView):
    """Xodimlar ro'yxati va yangi xodim qo'shish."""

    def get(self, request):
        tenant = request.user.tenant
        if not tenant:
            return Response({"results": []})
        employees = Employee.objects.filter(tenant=tenant, is_active=True).order_by("name")
        return Response({"results": EmployeeSerializer(employees, many=True).data})

    def post(self, request):
        serializer = EmployeeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        employee = serializer.save()
        return Response(EmployeeSerializer(employee).data, status=status.HTTP_201_CREATED)


class ShiftPreviewView(APIView):
    """Boshqa kassalardagi ochiq smena va savdolarni ko'rsatish."""

    def get(self, request):
        tenant = request.user.tenant
        today = timezone.localdate()

        my_shift = Shift.objects.filter(
            tenant=tenant, user=request.user, status=Shift.STATUS_OPEN
        ).first()

        other_open_shifts = Shift.objects.filter(
            tenant=tenant, status=Shift.STATUS_OPEN
        ).exclude(user=request.user)

        other_shift_open = other_open_shifts.exists()

        other_sales_total = Decimal("0")
        if other_shift_open:
            agg = Sale.objects.filter(
                tenant=tenant,
                status=Sale.STATUS_COMPLETED,
                shift__in=other_open_shifts,
            ).aggregate(s=Sum("total"))
            other_sales_total = agg["s"] or Decimal("0")
        else:
            agg = Sale.objects.filter(
                tenant=tenant,
                status=Sale.STATUS_COMPLETED,
                completed_at__date=today,
            ).exclude(user=request.user).aggregate(s=Sum("total"))
            other_sales_total = agg["s"] or Decimal("0")

        cash_balance, terminal_balance = suggested_opening_balances(tenant)

        my_shift_data = None
        my_summary = None
        if my_shift:
            my_shift_data = ShiftSerializer(my_shift).data
            my_summary = compute_shift_summary(my_shift)

        return Response(
            {
                "my_shift_open": my_shift is not None,
                "other_shift_open": other_shift_open,
                "other_sales_total": str(other_sales_total),
                "terminal_balance": str(terminal_balance),
                "cash_balance": str(cash_balance),
                "my_shift": my_shift_data,
                "my_summary": my_summary,
            }
        )


class ShiftOpenView(APIView):
    def post(self, request):
        serializer = ShiftOpenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        existing = Shift.objects.filter(
            tenant=request.user.tenant,
            user=request.user,
            status=Shift.STATUS_OPEN,
        ).first()
        if existing:
            return Response(ShiftSerializer(existing).data)

        shift = Shift.objects.create(
            tenant=request.user.tenant,
            user=request.user,
            opening_cash=data.get("opening_cash", 0),
            opening_terminal=data.get("opening_terminal", 0),
        )
        return Response(ShiftSerializer(shift).data, status=status.HTTP_201_CREATED)


class ShiftCurrentView(APIView):
    def get(self, request):
        shift = Shift.objects.filter(
            tenant=request.user.tenant,
            user=request.user,
            status=Shift.STATUS_OPEN,
        ).first()
        if not shift:
            return Response({"shift": None, "summary": None})
        return Response(
            {
                "shift": ShiftSerializer(shift).data,
                "summary": compute_shift_summary(shift),
            }
        )


class ShiftCloseView(APIView):
    def post(self, request):
        shift = Shift.objects.filter(
            tenant=request.user.tenant,
            user=request.user,
            status=Shift.STATUS_OPEN,
        ).first()
        if not shift:
            return Response(
                {"detail": "Ochiq smena topilmadi."},
                status=status.HTTP_404_NOT_FOUND,
            )

        summary = compute_shift_summary(shift)
        shift.status = Shift.STATUS_CLOSED
        shift.closed_at = timezone.now()
        shift.save(update_fields=["status", "closed_at"])

        return Response(
            {
                "shift": ShiftSerializer(shift).data,
                "summary": summary,
            }
        )
