from {{PACKAGE_NAME}}.device import resolve_device


def test_resolve_device_defaults_cpu_safely() -> None:
    assert resolve_device() in {"cpu", "mps", "cuda"}
