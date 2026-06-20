# Edge Cases Checklist — Memo Backend

Quick reference for what to test for each endpoint. Copy relevant rows into your test file.

## Records (`test_api_records.py` + `test_edge_cases.py`)

| # | Test Case | Expected | Fixture |
|---|-----------|----------|---------|
| 1 | Create record with valid data | 201, record in DB | `create_record` |
| 2 | Create record with non-existent `activity_id` | 404 or FK error | `create_client` |
| 3 | Create record with non-existent `client_id` | 404 or FK error | `create_activity` |
| 4 | Create record with empty visits array | 201, seats=0 | `create_activity`, `create_client` |
| 5 | Create record with phone (new client) | 201, client created | `create_activity` |
| 6 | Create record with phone (existing client) | 201, client reused | `create_activity`, `create_client` |
| 7 | Update record status | 200, status changed | `create_record` |
| 8 | Update record with invalid `status="banana"` | **422** | `create_record` |
| 9 | Delete record (soft delete) | 204, is_active=false | `create_record` |
| 10 | Get deleted record | 200, is_active=false | `create_record` |
| 11 | List records excludes deleted | deleted not in list | `create_record` |
| 12 | Create record exceeding capacity | 400 or business error | `create_activity` (capacity=1) |
| 13 | Create record with missing required fields | 422 | — |
| 14 | Update visit with `status="fake_status"` | **422** | `create_record` |
| 15 | Create record with all valid statuses | 201 for each | `create_activity`, `create_client` |
| 16 | Create record with multiple visits | 201, seats=N | `create_activity`, `create_client` |
| 17 | Concurrent record creation (capacity check) | Only N succeed | `create_activity` (capacity=N) |

## Clients (`test_api_clients.py`)

| # | Test Case | Expected | Fixture |
|---|-----------|----------|---------|
| 1 | Create client with valid data | 201 | `create_client` |
| 2 | Create client with duplicate phone | 409 or error | `create_client` |
| 3 | Create client without phone (empty string) | 201 | — |
| 4 | Search by phone — found | 200 + client data | `create_client` |
| 5 | Search by phone — not found | 404 | — |
| 6 | Update client name | 200, name changed | `create_client` |
| 7 | Delete client with active records | behavior defined | `create_record` |
| 8 | Create client with invalid `channel="banana"` | **422** | — |
| 9 | Create client with valid channel enum | 201 | — |
| 10 | List clients excludes deleted | deleted not in list | `create_client` |
| 11 | Get visitors for client | 200 + visitors list | `create_client` |

## Payments (`test_api_payments.py`)

| # | Test Case | Expected | Fixture |
|---|-----------|----------|---------|
| 1 | Create payment with valid data | 201 | `create_record` |
| 2 | Create payment with `amount=0` | **422** | `create_record` |
| 3 | Create payment with negative amount | **422** | `create_record` |
| 4 | Create payment for non-existent record | 404 | — |
| 5 | Delete payment (soft delete) | 204, is_active=false | `create_record` |
| 6 | Create multiple payments for same record | 201, all stored | `create_record` |
| 7 | Payment method validation (invalid `"crypto"`) | **422** | `create_record` |

## Activities (`test_api_activities.py`)

| # | Test Case | Expected | Fixture |
|---|-----------|----------|---------|
| 1 | Create activity with valid data | 201, occupied=0 | `create_activity` |
| 2 | Create activity with past date | 201 (allowed) | `create_activity` (past start) |
| 3 | Create activity with `capacity=0` | **422** | — |
| 4 | PATCH partial update | 200, only changed fields | `create_activity` |
| 5 | Date range filter | Only in-range activities | `create_activity` x3 |
| 6 | Occupied count matches records | occupied = count(records) | `create_activity`, `create_record` |

## Visitors (`test_api_visitors.py`)

| # | Test Case | Expected | Fixture |
|---|-----------|----------|---------|
| 1 | Create visitor with valid data | 201 | `create_client` |
| 2 | Create visitor without age (null) | 201, age=null | `create_client` |
| 3 | Create visitor with `age=0` | 201 (infant) | `create_client` |
| 4 | Delete visitor (soft delete) | 204 | `create_client` |
| 5 | Update visit status to invalid value | **422** | `create_record` |

## Quick Test Template

```python
"""Copy this template for each endpoint's edge case tests."""

class Test[Entity]EdgeCases:
    """Edge cases for /api/v1/[entities]."""

    def test_[entity]_with_missing_required_field(self, api_client) -> None:
        """POST with empty body returns 422."""
        response = api_client.post("/api/v1/[entities]", json={})
        assert response.status_code == 422

    def test_[entity]_with_invalid_enum(self, api_client, create_[prereq]) -> None:
        """POST with invalid enum value returns 422."""
        prereq = create_[prereq]()
        response = api_client.post("/api/v1/[entities]", json={
            ...prereq,
            "[enum_field]": "banana",
        })
        assert response.status_code == 422

    def test_[entity]_nonexistent_fk(self, api_client) -> None:
        """POST with non-existent FK returns 404 or 422."""
        response = api_client.post("/api/v1/[entities]", json={
            "[fk]_id": "nonexistent-id",
        })
        assert response.status_code in (404, 422, 500)
```
