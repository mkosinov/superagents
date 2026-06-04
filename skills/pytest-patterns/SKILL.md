---
name: pytest-patterns
description: >-
  Writing backend tests for Memo? Use this skill. Covers pytest fixtures,
  factory pattern, API testing with sync TestClient, integration tests,
  contract testing, and DB verification. Activate whenever the user asks
  to write, fix, or review any test in backend/tests/ — even if they don't
  say "pytest" explicitly. Also activate for conftest changes and coverage setup.
license: MIT
compatibility: 'Python 3.12+, pytest 8+, FastAPI TestClient, SQLite, aiosqlite'
metadata:
  author: platform-team
  version: '3.0.0'
  sdlc-phase: testing
allowed-tools: Read Edit Write Bash(pytest:*) Bash(python:*) Bash(uv:*)
context: fork
---

# Pytest Patterns — Memo Project

## Agent Decision Protocol

```
WHEN user asks to write a test:
  IF "endpoint" / "API" / "status code" / "CRUD"
    → write API test using api_client fixture (see API Test Template)
  IF "flow" / "phone" / "end-to-end" / "creates client automatically"
    → write integration test (see Integration Tests)
  IF "schema" / "contract" / "response shape"
    → write contract test (see Contract Testing)
  IF "DB" / "is_active" / "cascade" / "FK"
    → write API test + SQL verification (see DB Verification)
  IF unclear → ask: "Это проверка endpoint или полный флоу через несколько сущностей?"

BEFORE writing any test:
  READ references/conftest-template.py    ← factory signatures + query_db
  CHECK: does api_client fixture exist in conftest.py?
  NEVER call create_app() inside a test — always use api_client fixture

AFTER writing code:
  RUN uv run pytest tests/<file> -v
  FIX all failures before declaring done
```

---

## Project Structure

```
backend/tests/
├── conftest.py                    ← fixtures: reset_db, api_client, factories, query_db
├── fixtures/                      ← JSON seed data (masters, services, locations)
├── test_api_<entity>.py           ← CRUD tests per entity
├── test_edge_cases.py             ← validation, boundary, data integrity
├── test_record_creation_flow.py   ← integration: phone → client → record → visits
└── test_<feature>.py              ← other feature tests
```

**Naming conventions:**
- Files: `test_<module>.py`
- Classes: `Test<Feature>` (group related tests)
- Functions: `test_<action>_<expected_outcome>`

---

## Conftest Architecture

```
conftest.py (autouse)
├── reset_db          ← drop_all + create_all before EACH test (autouse=True)
├── api_client        ← TestClient(create_app()) — one per test, yielded
├── create_master     ← factory(**overrides) → dict
├── create_service    ← factory(**overrides) → dict
├── create_location   ← factory(**overrides) → dict
├── create_client     ← factory(**overrides) → dict  [unique phone via uuid]
├── create_activity   ← factory(**overrides) → dict  [composes master+service+location]
├── create_record     ← factory(**overrides) → dict  [composes activity+client]
└── query_db(sql)     ← list[dict]  [direct SQLite, not a fixture]
```

### Factory Signatures

| Factory | Key overrides | Returns |
|---------|---------------|---------|
| `create_master(**overrides)` | `first_name`, `last_name`, `color`, `position`, `specialty` | `dict` with `id`, `color`, … |
| `create_service(**overrides)` | `title`, `duration`, `min_age`, `max_age` | `dict` with `id`, `duration`, … |
| `create_location(**overrides)` | `name`, `address`, `capacity` | `dict` with `id`, … |
| `create_client(**overrides)` | `name`, `phone`, `channel` | `dict` with `id`, `phone`, … |
| `create_activity(**overrides)` | `capacity`, `is_private`, `start` (datetime), `duration` | `dict` with `id`, `master_id`, … |
| `create_record(**overrides)` | `comment`, `visits` (list of `{price, status, name?}`) | `dict` with `id`, `activity_id`, `client_id`, `visits`, … |

```python
# Overrides: pass any field to replace the default
record = create_record(comment="VIP")
record = create_record(visits=[
    {"name": "Алиса", "price": 3500, "status": "waiting"},
    {"name": "Борис", "price": 2500, "status": "waiting"},
])
activity = create_activity(capacity=5, is_private=True)
client = create_client(phone="+79991234567", channel="phone")

# Composing manually (rarely needed)
activity = create_activity()
record = create_record(activity_id=activity["id"])
```

---

## API Test Template

**ALWAYS use `api_client` fixture. NEVER call `create_app()` inside a test.**

```python
class TestPaymentsCrud:
    def test_create_payment(self, api_client, create_record) -> None:
        record = create_record()
        resp = api_client.post("/api/v1/payments", json={
            "record_id": record["id"],
            "amount": 3000,
            "method": "card",
        })
        assert resp.status_code == 201, f"Create failed: {resp.text}"
        body = resp.json()
        assert body["record_id"] == record["id"]
        assert body["amount"] == 3000
        assert body["method"] == "card"
        assert body["is_active"] is True

    def test_get_nonexistent_returns_404(self, api_client) -> None:
        resp = api_client.get("/api/v1/payments/nonexistent-id")
        assert resp.status_code == 404

    def test_delete_soft_deletes(self, api_client, create_record) -> None:
        record = create_record()
        payment = api_client.post("/api/v1/payments", json={
            "record_id": record["id"], "amount": 1000, "method": "cash",
        }).json()

        api_client.delete(f"/api/v1/payments/{payment['id']}")

        # Still accessible by ID but is_active=False
        resp = api_client.get(f"/api/v1/payments/{payment['id']}")
        assert resp.json()["is_active"] is False

        # Excluded from list
        ids = [p["id"] for p in api_client.get("/api/v1/payments").json()]
        assert payment["id"] not in ids
```

---

## Speed Guidelines

**Root cause of slow tests (>3min):** `create_app()` called inside each test.

Each `create_app()` + `TestClient(app)` creates a full ASGI app and boots lifespan events (~300-500ms). With 80 tests = 24-40 seconds just on app init. Use `api_client` fixture — it's created once per test via `conftest.py`.

| Pattern | Cost per test | Fix |
|---------|--------------|-----|
| `create_app()` inside test | ~400ms | Use `api_client` fixture |
| `_create_prerequisites()` helper | varies | Use composable factories |
| `create_record()` when only need activity | 5 API calls | Use `create_activity()` instead |

**Rule:** use the smallest factory that satisfies the test.

```python
# Slow: creates master+service+location+activity+client+record (6 calls)
def test_activity_occupied(self, api_client, create_record):
    record = create_record()
    ...

# Fast: creates only what's needed (4 calls)
def test_activity_no_records_occupied_zero(self, api_client, create_activity):
    activity = create_activity()
    resp = api_client.get(f"/api/v1/activities/{activity['id']}")
    assert resp.json()["occupied"] == 0
```

---

## Coverage Gate

Add to `pyproject.toml` (not yet configured in project):

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "--cov=src --cov-report=term-missing --cov-fail-under=80"
```

Or run manually:
```bash
uv run pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=80
```

Target: 80% line coverage minimum. Current state: unknown (not measured).

---

## Contract Testing

Verify that API responses match the declared Pydantic schemas:

```python
from src.schemas.records import RecordOut
from src.schemas.clients import ClientOut
from src.schemas.payments import PaymentOut

class TestResponseContracts:
    def test_record_response_matches_schema(self, api_client, create_record):
        record = create_record()
        resp = api_client.get(f"/api/v1/records/{record['id']}")
        assert resp.status_code == 200
        # Raises ValidationError if response doesn't match schema
        validated = RecordOut.model_validate(resp.json())
        assert str(validated.id) == record["id"]

    def test_record_list_items_match_schema(self, api_client, create_record):
        create_record()
        resp = api_client.get("/api/v1/records")
        for item in resp.json():
            RecordOut.model_validate(item)  # all items must validate
```

---

## Integration Tests

Full user flow tests — no mocks, real DB, multiple endpoints:

```python
class TestRecordCreationFlow:
    def test_phone_creates_client_and_visitors(
        self, api_client, create_activity
    ) -> None:
        """Real flow: phone → new client + visitors + record."""
        activity = create_activity()
        phone = "+79998887766"

        resp = api_client.post("/api/v1/records", json={
            "activity_id": activity["id"],
            "phone": phone,
            "visits": [
                {"name": "Алиса", "age": 28, "price": 3500},
                {"name": "Борис", "age": 35, "price": 3500},
            ],
        })
        assert resp.status_code == 201, f"Create failed: {resp.text}"
        record = resp.json()

        # Client auto-created with correct phone
        client_resp = api_client.get(f"/api/v1/clients/{record['client_id']}")
        assert client_resp.json()["phone"] == phone

        # Visitors created
        assert record["seats"] == 2
        assert len(record["visits"]) == 2

        # Activity occupied updated
        activity_resp = api_client.get(f"/api/v1/activities/{activity['id']}")
        assert activity_resp.json()["occupied"] == 1

    def test_phone_reuses_existing_client(
        self, api_client, create_activity, create_client
    ) -> None:
        """If client with this phone exists, reuse it."""
        activity = create_activity()
        existing = create_client(phone="+79991112233")

        resp = api_client.post("/api/v1/records", json={
            "activity_id": activity["id"],
            "phone": "+79991112233",
            "visits": [{"name": "Гость", "price": 3500}],
        })
        assert resp.status_code == 201
        assert resp.json()["client_id"] == existing["id"]
```

---

## DB Verification

| What to check | Use API | Use SQL (`query_db`) |
|---------------|---------|----------------------|
| Status updated | `GET /api/v1/records/{id}` | |
| Soft delete flag | | `SELECT is_active FROM records` |
| FK constraint | | `SELECT client_id FROM records` |
| Cascade behavior | | `SELECT * FROM visits WHERE record_id=... AND is_active=1` |
| Payment total | | `SELECT COALESCE(SUM(amount),0) FROM payments WHERE record_id=...` |

```python
from tests.conftest import query_db

def test_soft_delete_at_db_level(api_client, create_record):
    record = create_record()
    api_client.delete(f"/api/v1/records/{record['id']}")

    rows = query_db(f"SELECT is_active FROM records WHERE id='{record['id']}'")
    assert rows[0]["is_active"] == 0  # SQLite stores bool as 0/1
```

---

## FK Enforcement

**Current state:** SQLite FK constraints are OFF by default. `record` with nonexistent `activity_id` → 201 (should be 4xx).

**Fix** — add to `reset_db` fixture in `conftest.py`:

```python
from sqlalchemy import text

async def _reset() -> None:
    async with db_manager.engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
```

⚠️ **Before enabling:** audit tests that currently pass with invalid FK data (e.g., `test_create_record_invalid_activity` in `test_edge_cases.py` — it asserts 201, will break).

---

## Known Gaps Pattern

When a validation is missing in the schema, document it as a known gap — not a passing test:

```python
# BAD: silently accepts a bug
def test_zero_amount(self, api_client, create_record):
    record = create_record()
    resp = api_client.post("/api/v1/payments", json={
        "record_id": record["id"], "amount": 0, "method": "cash",
    })
    assert resp.status_code == 201  # passes but it's a bug

# GOOD: explicitly marks the gap
@pytest.mark.xfail(reason="TODO: add gt=0 validation to PaymentCreate schema", strict=True)
def test_zero_amount_should_be_rejected(self, api_client, create_record):
    record = create_record()
    resp = api_client.post("/api/v1/payments", json={
        "record_id": record["id"], "amount": 0, "method": "cash",
    })
    assert resp.status_code == 422
```

`strict=True` means: if the test unexpectedly passes (validation was added), CI fails and you update the marker.

---

## Enum Validation

For each enum field: (1) invalid value → 422, (2) all valid values → 200/201.

```python
class TestRecordStatusValidation:
    VALID_STATUSES = ["pending", "confirmed", "cancelled", "no_show"]

    @pytest.mark.parametrize("status", VALID_STATUSES)
    def test_valid_status_accepted(self, api_client, create_record, status) -> None:
        record = create_record()
        resp = api_client.put(f"/api/v1/records/{record['id']}", json={
            "activity_id": record["activity_id"],
            "client_id": record["client_id"],
            "status": status,
            "visits": record["visits"],
        })
        assert resp.status_code == 200, f"Status '{status}' rejected: {resp.text}"

    def test_invalid_status_rejected(self, api_client, create_record) -> None:
        record = create_record()
        resp = api_client.put(f"/api/v1/records/{record['id']}", json={
            "activity_id": record["activity_id"],
            "status": "banana",
            "visits": [],
        })
        assert resp.status_code == 422
```

**Enum fields:**

| Entity | Field | Valid values |
|--------|-------|-------------|
| Record | `status` | pending, confirmed, cancelled, no_show |
| Visit | `status` | waiting, visited, missed, cancelled |
| Payment | `method` | cash, card, transfer |
| Client | `channel` | telegram, phone, email, whatsapp, website |

---

## Common Mistakes

| # | Mistake | Fix |
|---|---------|-----|
| 1 | `create_app()` inside a test | Use `api_client` fixture from conftest |
| 2 | `_create_prerequisites()` helper function | Use composable fixture factories |
| 3 | Hardcoded phone `"+79991234567"` | `create_client()` uses `uuid` for unique phone |
| 4 | Not asserting status before parsing JSON | `assert resp.status_code == 201, f"Failed: {resp.text}"` |
| 5 | `create_record()` when only activity needed | Use `create_activity()` — 2 fewer API calls |
| 6 | Silent known gaps (asserting 201 on a bug) | Use `@pytest.mark.xfail(strict=True)` |
| 7 | Testing only happy path | Always test: 404 for missing, 422 for invalid input |
| 8 | Mocking the database | Use real test DB (`_TEST_DB_URL`). Mock only external HTTP/email |

---

## Running Tests

```bash
cd backend

# Basic
uv run pytest tests/ -v                          # all tests
uv run pytest tests/test_api_records.py -v        # one file
uv run pytest tests/ -v -x                        # stop on first failure
uv run pytest tests/ -k "payment" -v              # filter by name

# With coverage
uv run pytest tests/ --cov=src --cov-report=term-missing
uv run pytest tests/ --cov=src --cov-fail-under=80

# Integration tests only
uv run pytest tests/test_record_creation_flow.py -v
```

---

## Reference Files

Read on demand:

| File | Read when |
|------|-----------|
| `references/conftest-template.py` | Need full conftest with all factories and `query_db` |
| `references/api-test-template.py` | Need complete CRUD test class example |
| `references/integration-test-template.py` | Need phone→client→record flow examples |
| `references/memo-edge-cases.md` | Need edge case checklist per endpoint |
| `references/memo-enum-validation.py` | Need parametrized enum tests for all entities |
| `references/factory-template.py` | Need factory internals or how to add new factory |
| `references/service-test-template.py` | Need unit tests for service layer (non-API) |
