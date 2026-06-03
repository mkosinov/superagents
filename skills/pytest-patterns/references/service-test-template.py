"""
service-test-template.py — Service unit test with mocked repository (Memo domain).

Place at: backend/tests/unit/services/test_record_service.py

Memo uses this pattern for unit-testing service business logic in isolation.
Mock the repository layer (data access) so service tests run without a DB.

Note: Most Memo testing is done at the API level (integration tests).
Service-level unit tests are for complex business logic only.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


# ─── Fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_record_repo():
    """Mocked record repository with common async methods."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock()
    repo.list_all = AsyncMock(return_value=[])
    repo.count_by_activity = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_activity_repo():
    """Mocked activity repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.update_occupied = AsyncMock()
    return repo


@pytest.fixture
def record_service(mock_record_repo, mock_activity_repo):
    """RecordService with mocked dependencies."""
    from src.services.record_service import RecordService
    return RecordService(
        record_repo=mock_record_repo,
        activity_repo=mock_activity_repo,
    )


# ─── Create Record Tests ────────────────────────────────────────────────────────

class TestCreateRecord:
    """Tests for RecordService.create_record()."""

    async def test_create_record_success(self, record_service, mock_record_repo):
        """Creating a record with valid data succeeds."""
        mock_record_repo.create.return_value = {
            "id": "r1",
            "activity_id": "a1",
            "client_id": "c1",
            "status": "pending",
            "seats": 1,
        }

        result = await record_service.create_record(
            activity_id="a1",
            client_id="c1",
            visits=[{"price": 3500}],
        )

        assert result["status"] == "pending"
        mock_record_repo.create.assert_called_once()

    async def test_create_record_updates_occupied(
        self, record_service, mock_record_repo, mock_activity_repo
    ):
        """Creating a record updates activity.occupied count."""
        mock_record_repo.create.return_value = {
            "id": "r1", "activity_id": "a1",
            "client_id": "c1", "status": "pending", "seats": 2,
        }
        mock_record_repo.count_by_activity.return_value = 1

        await record_service.create_record(
            activity_id="a1",
            client_id="c1",
            visits=[{"price": 3500}, {"price": 2500}],
        )

        mock_activity_repo.update_occupied.assert_called_once_with("a1", 1)


# ─── Status Transition Tests ────────────────────────────────────────────────────

class TestRecordStatusTransition:
    """Tests for record status changes."""

    async def test_confirm_record(self, record_service, mock_record_repo):
        """Confirming a record changes status to 'confirmed'."""
        mock_record_repo.get_by_id.return_value = {
            "id": "r1", "status": "pending",
        }
        mock_record_repo.update.return_value = {
            "id": "r1", "status": "confirmed",
        }

        result = await record_service.update_status("r1", "confirmed")
        assert result["status"] == "confirmed"

    async def test_cancel_record(self, record_service, mock_record_repo):
        """Cancelling a record changes status to 'cancelled'."""
        mock_record_repo.get_by_id.return_value = {
            "id": "r1", "status": "confirmed",
        }
        mock_record_repo.update.return_value = {
            "id": "r1", "status": "cancelled",
        }

        result = await record_service.update_status("r1", "cancelled")
        assert result["status"] == "cancelled"


# ─── External Service Mocking ───────────────────────────────────────────────────

class TestRecordNotifications:
    """Tests for notification side effects during record operations."""

    async def test_confirmation_sms_sent(self, record_service, mock_record_repo):
        """An SMS is sent when a record is confirmed."""
        mock_record_repo.get_by_id.return_value = {
            "id": "r1", "status": "pending", "client_id": "c1",
        }
        mock_record_repo.update.return_value = {
            "id": "r1", "status": "confirmed",
        }

        with patch("src.services.record_service.SMSClient") as mock_sms_cls:
            mock_sms = mock_sms_cls.return_value
            mock_sms.send_confirmation = AsyncMock(return_value=True)

            await record_service.update_status("r1", "confirmed")

            mock_sms.send_confirmation.assert_called_once()

    async def test_record_confirmed_even_if_sms_fails(
        self, record_service, mock_record_repo
    ):
        """Record confirmation should not fail if SMS fails."""
        mock_record_repo.get_by_id.return_value = {
            "id": "r1", "status": "pending", "client_id": "c1",
        }
        mock_record_repo.update.return_value = {
            "id": "r1", "status": "confirmed",
        }

        with patch("src.services.record_service.SMSClient") as mock_sms_cls:
            mock_sms = mock_sms_cls.return_value
            mock_sms.send_confirmation = AsyncMock(
                side_effect=Exception("SMS gateway error")
            )

            # Should NOT raise despite SMS failure
            result = await record_service.update_status("r1", "confirmed")
            assert result["status"] == "confirmed"
