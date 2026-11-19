"""Health contract tests for {{PROJECT_NAME}}."""

from {{PACKAGE_NAME}}.main import health_status


def test_health_status_returns_ok() -> None:
    payload = health_status()
    assert payload["status"] == "ok"
