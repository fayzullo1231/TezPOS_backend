from django.urls import path

from .cash_views import CashLedgerView, CashSummaryView, CashTransactionCreateView
from .views import (
    HealthView,
    LoginView,
    MeView,
    RegisterView,
    ShiftCloseView,
    ShiftCurrentView,
    ShiftOpenView,
    ShiftPreviewView,
    EmployeeListCreateView,
    TenantCreateView,
    TenantInfoView,
    TenantStaffDetailView,
    TenantStaffListView,
)

urlpatterns = [
    path("health/", HealthView.as_view()),
    path("login/", LoginView.as_view()),
    path("register/", RegisterView.as_view()),
    path("tenants/", TenantCreateView.as_view()),
    path("me/", MeView.as_view()),
    path("tenant/", TenantInfoView.as_view()),
    path("staff/", TenantStaffListView.as_view()),
    path("staff/<uuid:user_id>/", TenantStaffDetailView.as_view()),
    path("employees/", EmployeeListCreateView.as_view()),
    path("shift/preview/", ShiftPreviewView.as_view()),
    path("shift/open/", ShiftOpenView.as_view()),
    path("shift/close/", ShiftCloseView.as_view()),
    path("shift/current/", ShiftCurrentView.as_view()),
    path("cash/ledger/", CashLedgerView.as_view()),
    path("cash/summary/", CashSummaryView.as_view()),
    path("cash/transactions/", CashTransactionCreateView.as_view()),
]
