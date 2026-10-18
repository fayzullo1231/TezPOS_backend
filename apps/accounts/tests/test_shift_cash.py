"""Smena kassa hisobi — qarz undirish, ochish/yopish, eski klient mosligi."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import CashTransaction, Shift, Tenant
from apps.accounts.shift_utils import compute_shift_summary
from apps.sales.models import Customer, CustomerDebtPayment, Sale


User = get_user_model()


def _dec(v):
    return Decimal(str(v))


class ShiftCashLogicTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            server_name="kassa-test", display_name="Kassa Test", is_active=True
        )
        self.user = User.objects.create_user(
            username="kassir1",
            password="x",
            tenant=self.tenant,
            role="cashier",
        )
        self.shift = Shift.objects.create(
            tenant=self.tenant,
            user=self.user,
            opening_cash=_dec("100000"),
            opening_terminal=_dec("0"),
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, name="Eski mijoz", debt=_dec("50000")
        )
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {self.user.api_token}",
            HTTP_X_SERVER_NAME=self.tenant.server_name,
        )

    def test_old_debt_collection_increases_expected_cash(self):
        CustomerDebtPayment.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            user=self.user,
            shift=self.shift,
            amount=_dec("50000"),
            payment_type=CustomerDebtPayment.PAYMENT_CASH,
            receipt_number=1,
            balance_after=_dec("0"),
        )
        self.customer.debt = _dec("0")
        self.customer.save(update_fields=["debt"])

        s = compute_shift_summary(self.shift)
        self.assertEqual(_dec(s["debt_collections_cash"]), _dec("50000"))
        self.assertEqual(_dec(s["expected_cash"]), _dec("150000"))
        self.assertEqual(_dec(s["debt_total"]), _dec("0"))

    def test_credit_sale_does_not_inflate_expected_cash(self):
        Sale.objects.create(
            tenant=self.tenant,
            user=self.user,
            shift=self.shift,
            status=Sale.STATUS_COMPLETED,
            payment_type=Sale.PAYMENT_CREDIT,
            total=_dec("30000"),
            paid_amount=_dec("0"),
            debt_amount=_dec("30000"),
            receipt_number=1,
        )
        s = compute_shift_summary(self.shift)
        self.assertEqual(_dec(s["sales_total"]), _dec("30000"))
        self.assertEqual(_dec(s["debt_total"]), _dec("30000"))
        self.assertEqual(_dec(s["cash_sales"]), _dec("0"))
        self.assertEqual(_dec(s["expected_cash"]), _dec("100000"))

    def test_expense_reduces_expected_cash(self):
        CashTransaction.objects.create(
            tenant=self.tenant,
            user=self.user,
            shift=self.shift,
            number=100001,
            transaction_type=CashTransaction.TYPE_EXPENSE,
            payment_method=CashTransaction.PAYMENT_CASH,
            category="Paket",
            amount=_dec("10000"),
        )
        s = compute_shift_summary(self.shift)
        self.assertEqual(_dec(s["expected_cash"]), _dec("90000"))

    def test_close_empty_body_legacy_compatible(self):
        Sale.objects.create(
            tenant=self.tenant,
            user=self.user,
            shift=self.shift,
            status=Sale.STATUS_COMPLETED,
            payment_type=Sale.PAYMENT_CASH,
            total=_dec("20000"),
            paid_amount=_dec("20000"),
            debt_amount=_dec("0"),
            receipt_number=2,
        )
        r = self.client.post("/api/auth/shift/close/", {}, format="json")
        self.assertEqual(r.status_code, 200)
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.status, Shift.STATUS_CLOSED)
        self.assertEqual(_dec(self.shift.closing_cash), _dec("120000"))
        self.assertEqual(_dec(self.shift.variance_cash), _dec("0"))

    def test_close_with_count_and_reason(self):
        r = self.client.post(
            "/api/auth/shift/close/",
            {
                "closing_cash": "95000",
                "closing_terminal": "0",
                "variance_reason": "Sanash farqi",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.shift.refresh_from_db()
        self.assertEqual(_dec(self.shift.closing_cash), _dec("95000"))
        self.assertEqual(_dec(self.shift.variance_cash), _dec("-5000"))
        self.assertIn("Sanash", self.shift.variance_reason)

    def test_close_variance_requires_reason(self):
        r = self.client.post(
            "/api/auth/shift/close/",
            {"closing_cash": "90000", "closing_terminal": "0"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_open_with_confirm_zero(self):
        self.shift.status = Shift.STATUS_CLOSED
        self.shift.closed_at = self.shift.opened_at
        self.shift.save()
        r = self.client.post(
            "/api/auth/shift/open/",
            {
                "opening_cash": "0",
                "opening_terminal": "0",
                "confirm_opening": True,
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(_dec(r.data["opening_cash"]), _dec("0"))

    def test_open_empty_uses_suggested(self):
        self.shift.status = Shift.STATUS_CLOSED
        self.shift.closed_at = self.shift.opened_at
        self.shift.closing_cash = _dec("77777")
        self.shift.closing_terminal = _dec("0")
        self.shift.save()
        r = self.client.post("/api/auth/shift/open/", {}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(_dec(r.data["opening_cash"]), _dec("77777"))

    def test_pay_debt_attaches_shift(self):
        r = self.client.post(
            f"/api/sales/customers/{self.customer.id}/pay-debt/",
            {"amount": "20000", "payment_type": "cash"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        pay = CustomerDebtPayment.objects.get(id=r.data["id"])
        self.assertEqual(pay.shift_id, self.shift.id)
        s = compute_shift_summary(self.shift)
        self.assertEqual(_dec(s["debt_collections_cash"]), _dec("20000"))
        self.assertEqual(_dec(s["expected_cash"]), _dec("120000"))

    def test_cash_tx_idempotent(self):
        body = {
            "transaction_type": "expense",
            "amount": "5000",
            "category": "Transport",
            "payment_method": "cash",
            "client_id": "idem-1",
        }
        r1 = self.client.post("/api/auth/cash/transactions/", body, format="json")
        r2 = self.client.post("/api/auth/cash/transactions/", body, format="json")
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(r1.data["id"], r2.data["id"])
        self.assertEqual(
            CashTransaction.objects.filter(tenant=self.tenant, client_id="idem-1").count(),
            1,
        )

    def test_cash_tx_requires_open_shift(self):
        self.shift.status = Shift.STATUS_CLOSED
        self.shift.save(update_fields=["status"])
        r = self.client.post(
            "/api/auth/cash/transactions/",
            {
                "transaction_type": "expense",
                "amount": "1000",
                "category": "Paket",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 400)
