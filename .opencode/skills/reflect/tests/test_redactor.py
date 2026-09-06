"""Tests for secret redactor."""
from reflect.scripts.lib.redactor import redact_secrets, REDACT_PATTERNS


def test_redacts_openai_keys():
    text = "Using key sk-1234567890abcdefghij for API call"
    out = redact_secrets(text)
    assert "sk-1234567890" not in out
    assert "[REDACTED]" in out


def test_redacts_google_api_keys():
    text = "GOOGLE_API_KEY=AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
    out = redact_secrets(text)
    assert "AIzaSy" not in out


def test_redacts_bearer_tokens():
    text = "Authorization: Bearer abc123def456ghi789jkl012mno345pqr"
    out = redact_secrets(text)
    assert "abc123def456" not in out


def test_redacts_password_env_vars():
    text = "DATABASE_PASSWORD=hunter2 PGPASSWORD=secret123"
    out = redact_secrets(text)
    assert "hunter2" not in out
    assert "secret123" not in out


def test_preserves_normal_text():
    text = "This is a normal log line about a successful commit"
    out = redact_secrets(text)
    assert out == text


def test_patterns_list_nonempty():
    assert len(REDACT_PATTERNS) >= 4
