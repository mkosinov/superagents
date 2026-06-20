"""
memo-enum-validation.py — Enum validation test templates for Memo.

Place at: backend/tests/test_edge_cases.py (or separate file)

Tests that all enum fields reject invalid values with 422.
These tests only make sense AFTER Phase 0 (enum validation in schemas) is done.

Enum fields:
  - Record.status: pending, confirmed, cancelled, no_show
  - Visit.status: waiting, visited, missed, cancelled
  - Payment.method: cash, card, transfer
  - Client.channel: telegram, phone, email, whatsapp, website
"""

import pytest


# ─── RecordStatus Validation ────────────────────────────────────────────────────

class TestRecordStatusValidation:
    """Record.status must be a valid RecordStatus enum value."""

    VALID_STATUSES = ["pending", "confirmed", "cancelled", "no_show"]

    @pytest.mark.parametrize("status", VALID_STATUSES)
    def test_valid_statuses(self, api_client, create_record, status) -> None:
        """All valid RecordStatus values are accepted."""
        record = create_record()
        response = api_client.put(f"/api/v1/records/{record['id']}", json={
            "activity_id": record["activity_id"],
            "client_id": record["client_id"],
            "status": status,
            "visits": [],
        })
        assert response.status_code == 200, (
            f"status='{status}' should be valid, got {response.status_code}: {response.text}"
        )
        assert response.json()["status"] == status

    def test_invalid_status_rejected(self, api_client, create_record) -> None:
        """status='banana' returns 422."""
        record = create_record()
        response = api_client.put(f"/api/v1/records/{record['id']}", json={
            "activity_id": record["activity_id"],
            "status": "banana",
            "visits": [],
        })
        assert response.status_code == 422

    def test_empty_status_rejected(self, api_client, create_record) -> None:
        """status='' returns 422."""
        record = create_record()
        response = api_client.put(f"/api/v1/records/{record['id']}", json={
            "activity_id": record["activity_id"],
            "status": "",
            "visits": [],
        })
        assert response.status_code == 422


# ─── VisitStatus Validation ─────────────────────────────────────────────────────

class TestVisitStatusValidation:
    """Visit.status must be a valid VisitStatus enum value."""

    VALID_STATUSES = ["waiting", "visited", "missed", "cancelled"]

    @pytest.mark.parametrize("status", VALID_STATUSES)
    def test_valid_statuses(self, api_client, create_record, status) -> None:
        """All valid VisitStatus values are accepted."""
        record = create_record()
        visit_id = record["visits"][0]["id"]
        response = api_client.put(
            f"/api/v1/visits/{visit_id}/status",
            json={"status": status},
        )
        assert response.status_code == 200, (
            f"visit status='{status}' should be valid, got {response.status_code}"
        )

    def test_invalid_visit_status(self, api_client, create_record) -> None:
        """status='fake_status' returns 422."""
        record = create_record()
        visit_id = record["visits"][0]["id"]
        response = api_client.put(
            f"/api/v1/visits/{visit_id}/status",
            json={"status": "fake_status"},
        )
        assert response.status_code == 422


# ─── PaymentMethod Validation ───────────────────────────────────────────────────

class TestPaymentMethodValidation:
    """Payment.method must be a valid PaymentMethod enum value."""

    VALID_METHODS = ["cash", "card", "transfer"]

    @pytest.mark.parametrize("method", VALID_METHODS)
    def test_valid_methods(self, api_client, create_record, method) -> None:
        """All valid PaymentMethod values are accepted."""
        record = create_record()
        response = api_client.post("/api/v1/payments", json={
            "record_id": record["id"],
            "amount": 1000,
            "method": method,
        })
        assert response.status_code == 201, (
            f"method='{method}' should be valid, got {response.status_code}: {response.text}"
        )

    def test_invalid_method(self, api_client, create_record) -> None:
        """method='crypto' returns 422."""
        record = create_record()
        response = api_client.post("/api/v1/payments", json={
            "record_id": record["id"],
            "amount": 1000,
            "method": "crypto",
        })
        assert response.status_code == 422

    def test_null_method_accepted(self, api_client, create_record) -> None:
        """method=null is accepted (optional field)."""
        record = create_record()
        response = api_client.post("/api/v1/payments", json={
            "record_id": record["id"],
            "amount": 1000,
            "method": None,
        })
        assert response.status_code == 201


# ─── Channel Validation ─────────────────────────────────────────────────────────

class TestChannelValidation:
    """Client.channel must be a valid Channel enum value."""

    VALID_CHANNELS = ["telegram", "phone", "email", "whatsapp", "website"]

    @pytest.mark.parametrize("channel", VALID_CHANNELS)
    def test_valid_channels(self, api_client, channel) -> None:
        """All valid Channel values are accepted."""
        import uuid
        response = api_client.post("/api/v1/clients", json={
            "name": f"Test {uuid.uuid4().hex[:6]}",
            "phone": f"+7999{uuid.uuid4().hex[:7]}",
            "channel": channel,
        })
        assert response.status_code == 201, (
            f"channel='{channel}' should be valid, got {response.status_code}: {response.text}"
        )

    def test_invalid_channel(self, api_client) -> None:
        """channel='banana' returns 422."""
        response = api_client.post("/api/v1/clients", json={
            "name": "Test",
            "phone": "+79990000000",
            "channel": "banana",
        })
        assert response.status_code == 422

    def test_invalid_channel_instagram(self, api_client) -> None:
        """channel='instagram' returns 422 (was valid in old seed data)."""
        response = api_client.post("/api/v1/clients", json={
            "name": "Test",
            "phone": "+79990000001",
            "channel": "instagram",
        })
        assert response.status_code == 422

    def test_invalid_channel_vk(self, api_client) -> None:
        """channel='vk' returns 422 (was valid in old seed data)."""
        response = api_client.post("/api/v1/clients", json={
            "name": "Test",
            "phone": "+79990000002",
            "channel": "vk",
        })
        assert response.status_code == 422
