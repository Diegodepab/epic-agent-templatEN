### Environment Variables (`.env`)

Copy `.env.example` to `.env` (automatically handled by `make setup`). Never commit `.env` to version control.

| Variable | Default | Required | Description |
| :--- | :--- | :---: | :--- |
| `APP_NAME` | `{{PROJECT_SLUG}}` | Yes | Application identifier used in logs and telemetry |
| `APP_ENV` | `development` | Yes | Runtime environment (`development`, `staging`, `production`, `test`) |
| `LOG_LEVEL` | `INFO` | No | Structured logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
