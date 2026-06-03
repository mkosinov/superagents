"""
api-test-template.py — Memo API test patterns with sync TestClient.

Place at: backend/tests/test_api_records.py (or similar)

Key differences from generic patterns:
  - Uses sync TestClient (NOT AsyncClient)
  - Uses Memo fixture factories (NOT factory_boy)
  - Uses Memo endpoints (/api/v1/records, /api/v1/clients, etc.)
  - Tests Memo domain (Records, Clients, Activities, Payments)

Templates included:
  - CRUD test class
  - Enum validation test class
  - Edge case test patterns
"""

import pytest


# ─── CRUD Test Template ─────────────────────────────────────────────────────────

class TestRecordsCrud:
    """Full CRUD round-trip for /api/v1/records."""

    def test_create_record_with_visits(self, api_client, create_record) -> None:
        """POST /api/v1/records creates and returns 201."""
        record = create_record()

        assert record["id"] is not None
        assert record["is_active"] is True
        assert record["status"] == "pending"
        assert record["seats"] == 1

    def test_get_record_by_id(self, api_client, create_record) -> None:
        """GET /api/v1/records/{id} returns the specific record."""
        created = create_record()

        response = api_client.get(f"/api/v1/records/{created['id']}")
        assert response.status_code == 200, f"GET failed: {response.text}"
        assert response.json()["id"] == created["id"]

    def test_list_records_includes_created(self, api_client, create_record) -> None:
        """GET /api/v1/records returns a list including created."""
        created = create_record()

        response = api_client.get("/api/v1/records")
        assert response.status_code == 200
        ids = [r["id"] for r in response.json()]
        assert created["id"] in ids

    def test_update_record_status(self, api_client, create_record) -> None:
        """PUT /api/v1/records/{id} updates status."""
        created = create_record()

        response = api_client.put(f"/api/v1/records/{created['id']}", json={
            "activity_id": created["activity_id"],
            "client_id": created["client_id"],
            "status": "confirmed",
            "visits": [],
        })
        assert response.status_code == 200, f"Update failed: {response.text}"
        assert response.json()["status"] == "confirmed"

    def test_delete_record_soft_deletes(self, api_client, create_record) -> None:
        """DELETE /api/v1/records/{id} soft-deletes (is_active=False)."""
        created = create_record()

        response = api_client.delete(f"/api/v1/records/{created['id']}")
        assert response.status_code == 204

        # Still accessible by ID but is_active=False
        resp = api_client.get(f"/api/v1/records/{created['id']}")
        assert resp.json()["is_active"] is False

        # Excluded from list
        resp = api_client.get("/api/v1/records")
        ids = [r["id"] for r in resp.json()]
        assert created["id"] not in ids

    def test_get_nonexistent_returns_404(self, api_client) -> None:
        """GET /api/v1/records/{fake_id} returns 404."""
        response = api_client.get("/api/v1/records/nonexistent-id")
        assert response.status_code == 404


# ─── Payment CRUD Template ──────────────────────────────────────────────────────

class TestPaymentsCrud:
    """CRUD tests for /api/v1/payments."""

    def test_create_payment(self, api_client, create_record) -> None:
        """POST /api/v1/payments creates a payment and returns 201."""
        record = create_record()

        response = api_client.post("/api/v1/payments", json={
            "record_id": record["id"],
            "amount": 3000,
            "method": "card",
        })

        assert response.status_code == 201, f"Create failed: {response.text}"
        body = response.json()
        assert body["record_id"] == record["id"]
        assert body["amount"] == 3000
        assert body["method"] == "card"

    def test_create_payment_zero_amount(self, api_client, create_record) -> None:
        """POST /api/v1/payments with amount=0 returns 422."""
        record = create_record()

        response = api_client.post("/api/v1/payments", json={
            "record_id": record["id"],
            "amount": 0,
            "method": "card",
        })

        assert response.status_code == 422

    def test_create_payment_negative_amount(self, api_client, create_record) -> None:
        """POST /api/v1/payments with negative amount returns 422."""
        record = create_record()

        response = api_client.post("/api/v1/payments", json={
            "record_id": record["id"],
            "amount": -100,
            "method": "card",
        })

        assert response.status_code == 422


# ─── Phone-Based Record Creation ────────────────────────────────────────────────

class TestPhoneRecordCreation:
    """Record creation via phone number (auto-creates client)."""

    def test_create_record_with_phone_new_client(
        self, api_client, create_activity
    ) -> None:
        """POST /api/v1/records with phone auto-creates client and visitors."""
        activity = create_activity()
        phone = "+79990001122"

        response = api_client.post("/api/v1/records", json={
            "activity_id": activity["id"],
            "phone": phone,
            "visits": [
                {"name": "Alice", "age": 28, "price": 1500},
            ],
        })

        assert response.status_code == 201, f"Create failed: {response.text}"
        body = response.json()
        assert body["client_id"] is not None

        # Verify client was created with the phone
        client_resp = api_client.get(f"/api/v1/clients/{body['client_id']}")
        assert client_resp.json()["phone"] == phone

    def test_create_record_with_phone_existing_client(
        self, api_client, create_activity, create_client
    ) -> None:
        """If client with this phone exists, reuse instead of creating new."""
        activity = create_activity()
        existing = create_client(phone="+79991112233")

        response = api_client.post("/api/v1/records", json={
            "activity_id": activity["id"],
            "phone": "+79991112233",
            "visits": [{"name": "Visitor", "price": 3500}],
        })

        assert response.status_code == 201
        assert response.json()["client_id"] == existing["id"]


# ─── Activity Tests ─────────────────────────────────────────────────────────────

class TestActivities:
    """Tests for /api/v1/activities."""

    def test_activity_occupied_increases(
        self, api_client, create_activity, create_client
    ) -> None:
        """Creating a record increases activity.occupied."""
        activity = create_activity()
        client = create_client()

        # Verify occupied=0
        resp = api_client.get(f"/api/v1/activities/{activity['id']}")
        assert resp.json()["occupied"] == 0

        # Create a record
        api_client.post("/api/v1/records", json={
            "activity_id": activity["id"],
            "client_id": client["id"],
            "visits": [{"price": 3500}],
        })

        # Verify occupied=1
        resp = api_client.get(f"/api/v1/activities/{activity['id']}")
        assert resp.json()["occupied"] == 1

    def test_list_activities_date_range(
        self, api_client, create_activity
    ) -> None:
        """GET /api/v1/activities?date_from=...&date_to=... filters correctly."""
        from datetime import UTC, datetime, timedelta

        today = datetime.now(UTC).replace(hour=10, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        next_week = today + timedelta(days=7)

        create_activity(start=today)
        create_activity(start=tomorrow)
        create_activity(start=next_week)

        response = api_client.get("/api/v1/activities", params={
            "date_from": today.strftime("%Y-%m-%d"),
            "date_to": tomorrow.strftime("%Y-%m-%d"),
        })

        assert response.status_code == 200
        assert len(response.json()) == 2
