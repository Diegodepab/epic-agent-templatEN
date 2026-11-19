"""Smoke tests for {{PROJECT_NAME}}."""

from {{PACKAGE_NAME}}.cli import main


def test_cli_version_flag(capsys) -> None:
    code = main(["--version"])
    captured = capsys.readouterr()
    assert code == 0
    assert "0.1.0" in captured.out
