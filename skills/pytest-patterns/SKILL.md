---
name: pytest-patterns
description: >-
  Python backend testing patterns with pytest for FastAPI applications. Use when writing
  Python tests: unit tests for services and repositories, integration tests for API
  endpoints with TestClient (sync), fixture creation, fixture-based factories,
  mocking strategies, parametrized tests, enum validation, and DB verification via SQL.
  Covers Memo-specific patterns: Records, Clients, Activities, Payments, Visitors.
  Does NOT cover frontend tests (use vitest-playwright-patterns)
  or E2E browser tests (use vitest-playwright-patterns).
license: MIT
compatibility: 'Python 3.12+, pytest 8+, FastAPI TestClient, SQLite, aiosqlite'
metadata:
  author: platform-team
  version: '2.0.0'
  sdlc-phase: testing
allowed-tools: Read Edit Write Bash(pytest:*) Bash(python:*)
context: fork
---

# Pytest Patterns — Memo Project

## When to Use

Activate this skill when:
- Writing API tests for Memo endpoints (Records, Clients, Activities, Payments)
- Creating or refactoring pytest fixtures and conftest files
- Setting up fixture-based factories for test data
- Testing enum validation (RecordStatus, VisitStatus, PaymentMethod, Channel)
- Writing integration tests (phone → client → record → visits flow)
- Writing data integrity tests (FK constraints, soft delete, cascade)
- Adding parametrized tests for enum/input variations
- Verifying DB state via direct SQL

Do NOT use this skill for:
- Frontend React component tests (use `vitest-playwright-patterns`)
- E2E browser tests with Playwright (use `vitest-playwright-patterns`)

## Instructions

### Test Organization

```
backend/tests/
├── conftest.py                    # Fixture factories + DB reset
├── fixtures/
│   ├── masters.json               # Reference data
│   ├── services.json
│   ├── locations.json
│   └── seed.py                    # Loads reference data via API
├── test_api_records.py            # CRUD + phone flow
├── test_api_clients.py            # CRUD + phone search + channel validation
├── test_api_payments.py           # CRUD + amount validation
├── test_api_visitors.py           # CRUD + age edge cases
├── test_api_activities.py         # CRUD + date filtering + occupied
├── test_api_services.py           # CRUD + tariffs
├── test_api_masters.py            # CRUD
├── test_api_locations.py          # CRUD
├── test_edge_cases.py             # Cross-endpoint validation
├── test_record_creation_flow.py   # Integration: phone → client → record → visits
└── test_data_integrity.py         # FK constraints, soft delete, cascade
```

**Naming conventions:**
- Test files: `test_<module>.py`
- Test classes: `Test<Feature>` (group related tests)
- Test functions: `test_<action>_<expected_outcome>`
- Fixtures: descriptive noun (`api_client`, `create_record`)

### Conftest Architecture

```
conftest.py (autouse)
├── reset_db          ← drops/recreates ALL tables before EACH test
├── api_client        ← TestClient(app) — shared per test
├── create_master     ← factory fixture
├── create_service    ← factory fixture
├── create_location   ← factory fixture
├── create_client     ← factory fixture
├── create_activity   ← factory (creates master+service+location+activity)
└── create_record     ← factory (creates activity+client+record+visit)
```

**Key principle:** Fixtures are composable. `create_record` depends on `create_activity` which depends on `create_master`, `create_service`, `create_location`. Pytest resolves the chain automatically.

**Database lifecycle:** `reset_db` (autouse) drops and recreates all tables before each test. Zero data leaking between tests. Uses `drop_all + create_all`, NOT rollback.

### Fixture Scopes

| Scope | Use For | Example |
|-------|---------|---------|
| `function` (default) | Isolated per-test data | `api_client`, `create_record` |
| `session` | Shared across entire run | `engine` |

**Rules:**
- Default to `function` scope for data isolation
- `reset_db` is `autouse=True` — runs before every test automatically
- Never use `session` scope for mutable data

### Fixture Factory Pattern

Each factory is a pytest fixture that returns a callable. The callable creates an entity via API and returns the response JSON.

```python
@pytest.fixture
def create_master(api_client):
    def factory(**overrides):
        payload = {
            "first_name": "Test", "last_name": "Master",
            "color": "#5B8C7A", "position": "мастер",
            "specialty": "живопись", **overrides,
        }
        resp = api_client.post("/api/v1/masters", json=payload)
        assert resp.status_code == 201, f"Failed: {resp.text}"
        return resp.json()
    return factory
```

**Usage — BEFORE vs AFTER:**

```python
# BEFORE: 40 lines of boilerplate per test
def test_create_record():
    app = create_app()
    with TestClient(app) as client:
        master = client.post("/api/v1/masters", json={...}).json()
        # ... 30 more lines of setup ...
        response = client.post("/api/v1/records", json={...})

# AFTER: 5 lines, readable
def test_create_record(create_record):
    record = create_record()
    assert record["status"] == "pending"
    assert record["seats"] == 1
```

### API Test Pattern (Sync TestClient)

Memo uses **sync** `TestClient`, NOT `AsyncClient`.

```python
class TestRecordsCrud:
    def test_create_record(self, api_client, create_record) -> None:
        record = create_record()
        assert record["id"] is not None
        assert record["is_active"] is True

    def test_get_record_by_id(self, api_client, create_record) -> None:
        created = create_record()
        response = api_client.get(f"/api/v1/records/{created['id']}")
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    def test_delete_record_soft_deletes(self, api_client, create_record) -> None:
        created = create_record()
        response = api_client.delete(f"/api/v1/records/{created['id']}")
        assert response.status_code == 204
        # Still accessible but is_active=False
        resp = api_client.get(f"/api/v1/records/{created['id']}")
        assert resp.json()["is_active"] is False
        # Excluded from list
        resp = api_client.get("/api/v1/records")
        ids = [r["id"] for r in resp.json()]
        assert created["id"] not in ids
```

**Key patterns:**
- Assert status code FIRST, then response body
- Add error context: `assert resp.status_code == 201, f"Create failed: {resp.status_code}: {resp.text}"`
- Test error paths: 404, 409, 422
- Never assert on exact timestamps or auto-generated IDs

### Enum Validation Testing

For each enum field, verify: (1) valid values → 201/200, (2) invalid value → 422, (3) all valid values work.

```python
class TestRecordStatusValidation:
    VALID_STATUSES = ["pending", "confirmed", "cancelled", "no_show"]

    @pytest.mark.parametrize("status", VALID_STATUSES)
    def test_valid_statuses(self, api_client, create_record, status) -> None:
        record = create_record()
        response = api_client.put(f"/api/v1/records/{record['id']}", json={
            "activity_id": record["activity_id"],
            "client_id": record["client_id"],
            "status": status, "visits": [],
        })
        assert response.status_code == 200

    def test_invalid_status_rejected(self, api_client, create_record) -> None:
        record = create_record()
        response = api_client.put(f"/api/v1/records/{record['id']}", json={
            "activity_id": record["activity_id"],
            "status": "banana", "visits": [],
        })
        assert response.status_code == 422
```

**Enum fields to validate:**

| Entity | Field | Valid Values |
|--------|-------|-------------|
| Record | `status` | pending, confirmed, cancelled, no_show |
| Visit | `status` | waiting, visited, missed, cancelled |
| Payment | `method` | cash, card, transfer |
| Client | `channel` | telegram, phone, email, whatsapp, website |

### DB Verification

**Two approaches — use the right one:**

| Approach | When to use |
|----------|-------------|
| **API verification** (default) | Simple CRUD checks |
| **Direct SQL** | FK constraints, cascade, soft delete, concurrent state |

```python
import sqlite3

def query_db(sql: str) -> list[dict]:
    from tests.conftest import _db_file
    conn = sqlite3.connect(_db_file.name)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# Usage: verify soft delete at DB level
def test_soft_delete_at_db_level(api_client, create_record):
    record = create_record()
    api_client.delete(f"/api/v1/records/{record['id']}")
    rows = query_db(f"SELECT is_active FROM records WHERE id='{record['id']}'")
    assert rows[0]["is_active"] == 0  # SQLite stores bool as 0/1
```

### Mocking Strategy

**Mock external services — YES:**
```python
from unittest.mock import patch, AsyncMock

def test_notification_sent(api_client, create_record):
    with patch("src.services.notification.EmailClient") as mock_email:
        mock_email.return_value.send = AsyncMock(return_value=True)
        # ... test logic ...
```

**Mock the database — NO:**
Use real test database (SQLite temp file). Never mock repos in API tests.

| Mock | Do Not Mock |
|------|-------------|
| HTTP APIs, Email/SMS | Database queries |
| File storage (S3) | SQLAlchemy sessions |
| Time (`freezegun`) | Pydantic validation |

### Parametrized Tests

```python
@pytest.mark.parametrize("status,expected_code", [
    pytest.param("pending", 200, id="pending-ok"),
    pytest.param("confirmed", 200, id="confirmed-ok"),
    pytest.param("banana", 422, id="invalid-rejected"),
])
def test_record_status(api_client, create_record, status, expected_code):
    record = create_record()
    response = api_client.put(f"/api/v1/records/{record['id']}", json={
        "activity_id": record["activity_id"],
        "status": status, "visits": [],
    })
    assert response.status_code == expected_code
```

### Coverage Requirements

| Module | Target |
|--------|--------|
| Backend API endpoints | 90% line coverage |
| Backend schemas/validation | 95% |

```bash
cd backend && uv run pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=80
```

### Common Mistakes

| # | Mistake | Fix |
|---|---------|-----|
| 1 | Creating app in every test (40 lines boilerplate) | Use `api_client` + `create_record` fixtures |
| 2 | Hardcoding IDs (`"specific-id-123"`) | Create data first, use returned ID |
| 3 | Not checking status before parsing JSON | `assert resp.status_code == 201, f"Failed: {resp.text}"` |
| 4 | Testing only happy path | Also test invalid data (amount=-100, status="banana") |
| 5 | Duplicating prerequisite creation | Use composable fixtures (`create_activity`) |
| 6 | No error context in assertions | `assert x == 201, f"Create failed: {resp.status_code} {resp.text}"` |

### Test Anti-Patterns

**1. Testing implementation details:**
```python
# BAD: Tests internal method calls
def test_service_calls_repo(mock_repo):
    service.create_record(data)
    mock_repo.insert.assert_called_once_with(...)

# GOOD: Tests observable behavior
def test_create_record(api_client, create_activity, create_client):
    activity = create_activity()
    client = create_client()
    response = api_client.post("/api/v1/records", json={...})
    assert response.status_code == 201
```

**2. Shared mutable state between tests:**
Each test must be isolated. `reset_db` (autouse) ensures this. Never use module-level mutable data.

**3. Overly broad assertions:**
```python
# BAD
assert response.status_code == 200  # Only checks status

# GOOD
assert response.status_code == 200
data = response.json()
assert data["status"] == "confirmed"
assert data["seats"] == 1
```

### Running Tests

```bash
cd backend
uv run pytest tests/ -v                          # All tests
uv run pytest tests/test_api_records.py -v        # One file
uv run pytest tests/test_api_records.py::TestRecordsCrud -v  # One class
uv run pytest tests/ -v -x                        # Stop on first failure
uv run pytest tests/ --cov=src --cov-report=term-missing  # With coverage
uv run pytest tests/test_edge_cases.py -v         # Edge cases only
```

## Examples

See `references/conftest-template.py` for Memo conftest with fixture factories.
See `references/factory-template.py` for Memo fixture factory patterns.
See `references/api-test-template.py` for Memo API test patterns (sync TestClient).
See `references/service-test-template.py` for service unit test patterns.
See `references/integration-test-template.py` for Memo integration tests (phone flow).
See `references/memo-edge-cases.md` for edge case checklist by endpoint.
See `references/memo-enum-validation.py` for enum validation test templates.
