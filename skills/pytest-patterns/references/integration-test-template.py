"""
integration-test-template.py — Memo integration test: phone-based record creation flow.

Place at: backend/tests/test_record_creation_flow.py

This template demonstrates the FULL user flow as an integration test:
  1. Phone number → auto-create client
  2. Add visitors
  3. Create record with visits
  4. Verify all entities created correctly
  5. Verify via API + direct SQL

No mocks — every layer executes real code against a real test database.
"""

import pytest
import sqlite3


def query_db(sql: str) -> list[dict]:
    """Execute SQL against the test database."""
    from tests.conftest import _db_file
    conn = sqlite3.connect(_db_file.name)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Record Creation Flow ───────────────────────────────────────────────────────

class TestRecordCreationFlow:
    """End-to-end record creation as a real user would do it."""

    def test_phone_creates_client_and_visitors(
        self, api_client, create_activity
    ) -> None:
        """
        Real user flow:
        1. Admin selects an activity
        2. Admin enters phone number
        3. Admin adds visitor names
        4. Admin submits
        5. System creates: client + visitors + record + visits
        """
        activity = create_activity()
        phone = "+79998887766"

        # Step 1: Create record with phone
        response = api_client.post("/api/v1/records", json={
            "activity_id": activity["id"],
            "phone": phone,
            "comment": "Integration test",
            "visits": [
                {"name": "Алиса", "age": 28, "price": 3500},
                {"name": "Борис", "age": 35, "price": 3500},
            ],
        })
        assert response.status_code == 201, f"Create failed: {response.text}"
        record = response.json()

        # Step 2: Verify client was created
        assert record["client_id"] is not None
        client_resp = api_client.get(f"/api/v1/clients/{record['client_id']}")
        assert client_resp.status_code == 200
        client = client_resp.json()
        assert client["phone"] == phone

        # Step 3: Verify visitors were created
        assert record["seats"] == 2
        assert len(record["visits"]) == 2
        for visit in record["visits"]:
            visitor_resp = api_client.get(f"/api/v1/visitors/{visit['visitor_id']}")
            assert visitor_resp.status_code == 200

        # Step 4: Verify activity occupied increased
        activity_resp = api_client.get(f"/api/v1/activities/{activity['id']}")
        assert activity_resp.json()["occupied"] == 1

    def test_phone_reuses_existing_client(
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


# ─── Data Integrity Tests ───────────────────────────────────────────────────────

class TestForeignKeyConstraints:
    """Verify FK constraints prevent orphaned records."""

    def test_record_requires_valid_activity(
        self, api_client, create_client
    ) -> None:
        """Cannot create record with non-existent activity_id."""
        client = create_client()
        response = api_client.post("/api/v1/records", json={
            "activity_id": "nonexistent-activity",
            "client_id": client["id"],
            "visits": [{"price": 1000}],
        })
        # Should fail — either 404 (business check) or 422/500 (FK constraint)
        assert response.status_code in (404, 422, 500)


class TestSoftDelete:
    """Verify soft delete behavior via API + SQL."""

    def test_deleted_record_excluded_from_list(
        self, api_client, create_record
    ) -> None:
        record = create_record()
        api_client.delete(f"/api/v1/records/{record['id']}")

        response = api_client.get("/api/v1/records")
        ids = [r["id"] for r in response.json()]
        assert record["id"] not in ids

    def test_deleted_record_still_in_db(
        self, api_client, create_record
    ) -> None:
        """Soft delete sets is_active=0, doesn't remove row."""
        record = create_record()
        api_client.delete(f"/api/v1/records/{record['id']}")

        rows = query_db(f"SELECT * FROM records WHERE id='{record['id']}'")
        assert len(rows) == 1
        assert rows[0]["is_active"] == 0

    def test_deleted_client_excluded_from_list(
        self, api_client, create_client
    ) -> None:
        client = create_client()
        api_client.delete(f"/api/v1/clients/{client['id']}")

        response = api_client.get("/api/v1/clients")
        ids = [c["id"] for c in response.json()]
        assert client["id"] not in ids


# ─── Cascade Verification via SQL ───────────────────────────────────────────────

class TestCascadeBehavior:
    """Verify cascade/soft-delete behavior at DB level."""

    def test_delete_record_also_soft_deletes_visits(
        self, api_client, create_record
    ) -> None:
        """Deleting a record should also soft-delete its visits."""
        record = create_record()
        record_id = record["id"]

        # Verify visits exist
        visits_before = query_db(
            f"SELECT * FROM visits WHERE record_id='{record_id}' AND is_active=1"
        )
        assert len(visits_before) > 0

        # Delete record
        api_client.delete(f"/api/v1/records/{record_id}")

        # Visits should be soft-deleted too
        visits_after = query_db(
            f"SELECT * FROM visits WHERE record_id='{record_id}' AND is_active=1"
        )
        assert len(visits_after) == 0

    def test_payment_total_via_sql(
        self, api_client, create_record
    ) -> None:
        """Verify payment total calculation via SQL."""
        record = create_record()

        # Add two payments
        api_client.post("/api/v1/payments", json={
            "record_id": record["id"], "amount": 2000, "method": "card",
        })
        api_client.post("/api/v1/payments", json={
            "record_id": record["id"], "amount": 1500, "method": "cash",
        })

        # Verify total via SQL
        result = query_db(
            f"SELECT COALESCE(SUM(amount), 0) as total "
            f"FROM payments WHERE record_id='{record['id']}' AND is_active=1"
        )
        assert result[0]["total"] == 3500
