def test_backend_package_importable() -> None:
    import {{PACKAGE_NAME}}  # noqa: PLC0415

    assert {{PACKAGE_NAME}} is not None
