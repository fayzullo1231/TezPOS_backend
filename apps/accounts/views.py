from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sales.models import Sale

from .models import Employee, Shift, Tenant, User
from .shift_utils import (
    compute_shift_summary,
    default_opening_balances,
    suggested_opening_balances,
)
from .permissions import IsTenantAdmin
from .serializers import (
    EmployeeSerializer,
    LoginSerializer,
    RegisterSerializer,
    ShiftCloseSerializer,
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


class EmployeePayInfoView(APIView):
    """Oylik/avans: hisoblangan, to'langan, qolgan — qayta yaratmaslik uchun."""

    def get(self, request, employee_id):
        from apps.accounts.models import CashTransaction

        tenant = request.user.tenant
        emp = Employee.objects.filter(pk=employee_id, tenant=tenant, is_active=True).first()
        if not emp:
            return Response({"detail": "Xodim topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        paid = (
            CashTransaction.objects.filter(
                tenant=tenant,
                party_type="employee",
                party_name__iexact=emp.name,
                transaction_type=CashTransaction.TYPE_EXPENSE,
                occurred_at__gte=month_start,
            ).aggregate(s=Sum("amount"))["s"]
            or Decimal("0")
        )
        salary = emp.salary_amount or Decimal("0")
        remaining = salary - paid
        if remaining < 0:
            remaining = Decimal("0")
        return Response(
            {
                "employee": EmployeeSerializer(emp).data,
                "salary_amount": str(salary),
                "paid_this_month": str(paid),
                "remaining": str(remaining),
                "month": month_start.strftime("%Y-%m"),
            }
        )


class ShiftPreviewView(APIView):
    """Boshqa kassalardagi ochiq smena va savdolarni ko'rsatish."""

    def get(self, request):
        tenant = request.user.tenant

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

        suggested_cash, suggested_terminal = suggested_opening_balances(tenant)
        default_cash, default_terminal = default_opening_balances(tenant)

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
                # Eski klientlar uchun: taklif = oxirgi kutilgan
                "terminal_balance": str(suggested_terminal),
                "cash_balance": str(suggested_cash),
                "suggested_cash": str(suggested_cash),
                "suggested_terminal": str(suggested_terminal),
                "default_cash": str(default_cash),
                "default_terminal": str(default_terminal),
                "my_shift": my_shift_data,
                "my_summary": my_summary,
            }
        )


class ShiftOpenView(APIView):
    def post(self, request):
        existing = Shift.objects.filter(
            tenant=request.user.tenant,
            user=request.user,
            status=Shift.STATUS_OPEN,
        ).first()
        if existing:
            return Response(ShiftSerializer(existing).data)

        tenant = request.user.tenant
        suggested_cash, suggested_terminal = suggested_opening_balances(tenant)
        body = request.data if isinstance(request.data, dict) else {}
        ser = ShiftOpenSerializer(data=body)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data

        # Eski klient: bo'sh {} → avvalgidek suggested (moslik)
        # Yangi klient: confirm_opening yoki opening_* yuboradi (0 ham mumkin)
        confirm = bool(data.get("confirm_opening"))
        has_opening_keys = any(
            k in body for k in ("opening_cash", "opening_terminal", "confirm_opening")
        )
        if confirm or has_opening_keys:
            opening_cash = data.get("opening_cash", Decimal("0"))
            opening_terminal = data.get("opening_terminal", Decimal("0"))
        else:
            opening_cash, opening_terminal = suggested_cash, suggested_terminal

        shift = Shift.objects.create(
            tenant=tenant,
            user=request.user,
            opening_cash=opening_cash or Decimal("0"),
            opening_terminal=opening_terminal or Decimal("0"),
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


def _shift_user_name(user: User) -> str:
    name = (user.first_name or "").strip()
    return name or user.username


class ShiftHistoryView(APIView):
    """Joriy foydalanuvchining smenalari — har bir ochish/yopish alohida qator."""

    def get(self, request):
        tenant = request.user.tenant
        user = request.user

        # Bir foydalanuvchida faqat 1 ta ochiq smena — eski orphanlarni yopamiz
        open_shifts = list(
            Shift.objects.filter(
                tenant=tenant, user=user, status=Shift.STATUS_OPEN
            ).order_by("-opened_at")
        )
        for orphan in open_shifts[1:]:
            orphan.status = Shift.STATUS_CLOSED
            if not orphan.closed_at:
                orphan.closed_at = timezone.now()
            orphan.save(update_fields=["status", "closed_at"])

        show_all = request.query_params.get("all") == "true"
        is_admin = user.role in ("super_admin", "admin") or user.is_superuser
        if show_all and is_admin:
            qs = Shift.objects.filter(tenant=tenant).select_related("user")
        else:
            qs = Shift.objects.filter(tenant=tenant, user=user).select_related("user")

        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        if date_from:
            qs = qs.filter(opened_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(opened_at__date__lte=date_to)

        shifts = list(qs.order_by("-opened_at")[:200])
        open_count = sum(1 for s in shifts if s.status == Shift.STATUS_OPEN)
        closed_count = sum(1 for s in shifts if s.status == Shift.STATUS_CLOSED)

        results = []
        for shift in shifts:
            summary = compute_shift_summary(shift)
            row = {
                "id": str(shift.id),
                "opened_at": shift.opened_at,
                "closed_at": shift.closed_at,
                "status": shift.status,
                "opening_cash": str(shift.opening_cash),
                "opening_terminal": str(shift.opening_terminal),
                "user_id": str(shift.user_id),
                "user_name": _shift_user_name(shift.user),
                "summary": summary,
            }
            if shift.closing_cash is not None:
                row["closing_cash"] = str(shift.closing_cash)
                row["actual_total"] = str(
                    (shift.closing_cash or Decimal("0"))
                    + (shift.closing_terminal or Decimal("0"))
                )
            if shift.closing_terminal is not None:
                row["closing_terminal"] = str(shift.closing_terminal)
            if shift.variance_cash is not None or shift.variance_terminal is not None:
                vc = shift.variance_cash or Decimal("0")
                vt = shift.variance_terminal or Decimal("0")
                row["difference"] = str(vc + vt)
            results.append(row)

        return Response(
            {
                "count": len(results),
                "open_count": open_count,
                "closed_count": closed_count,
                "results": results,
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
        exp_cash = Decimal(str(summary["expected_cash"]))
        exp_term = Decimal(str(summary["expected_terminal"]))
        exp_total = exp_cash + exp_term

        body = request.data if isinstance(request.data, dict) else {}
        ser = ShiftCloseSerializer(data=body)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data

        # Eski klient: {} → sanangan = kutilgan (tafovut 0)
        has_close_keys = any(
            k in body for k in ("closing_cash", "closing_terminal", "actual_cash", "actual_terminal")
        )
        if has_close_keys:
            closing_cash = data.get("closing_cash")
            if closing_cash is None:
                closing_cash = data.get("actual_cash")
            closing_terminal = data.get("closing_terminal")
            if closing_terminal is None:
                closing_terminal = data.get("actual_terminal")
            if closing_cash is None:
                closing_cash = exp_cash
            if closing_terminal is None:
                closing_terminal = exp_term
        else:
            closing_cash, closing_terminal = exp_cash, exp_term

        closing_cash = Decimal(str(closing_cash or 0))
        closing_terminal = Decimal(str(closing_terminal or 0))
        variance_cash = closing_cash - exp_cash
        variance_terminal = closing_terminal - exp_term
        variance_total = variance_cash + variance_terminal
        reason = (data.get("variance_reason") or "").strip()

        if abs(variance_total) >= Decimal("0.01") and not reason and has_close_keys:
            return Response(
                {
                    "detail": "Tafovut bor. Sababini yozing.",
                    "expected_cash": str(exp_cash),
                    "expected_terminal": str(exp_term),
                    "expected_total": str(exp_total),
                    "closing_cash": str(closing_cash),
                    "closing_terminal": str(closing_terminal),
                    "variance_total": str(variance_total),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        shift.status = Shift.STATUS_CLOSED
        shift.closed_at = timezone.now()
        shift.closing_cash = closing_cash
        shift.closing_terminal = closing_terminal
        shift.variance_cash = variance_cash
        shift.variance_terminal = variance_terminal
        shift.variance_reason = reason
        shift.closed_by = request.user
        shift.save(
            update_fields=[
                "status",
                "closed_at",
                "closing_cash",
                "closing_terminal",
                "variance_cash",
                "variance_terminal",
                "variance_reason",
                "closed_by",
            ]
        )

        summary = compute_shift_summary(shift)
        summary["closing_cash"] = str(closing_cash)
        summary["closing_terminal"] = str(closing_terminal)
        summary["closing_total"] = str(closing_cash + closing_terminal)
        summary["variance_cash"] = str(variance_cash)
        summary["variance_terminal"] = str(variance_terminal)
        summary["variance_total"] = str(variance_total)
        if reason:
            summary["variance_reason"] = reason

        return Response(
            {
                "shift": ShiftSerializer(shift).data,
                "summary": summary,
            }
        )
