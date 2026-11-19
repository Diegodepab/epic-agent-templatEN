### Container Profiles (`compose.yaml`)

| Profile | Command | Purpose |
| :--- | :--- | :--- |
| `deps` | `make up-deps` | Starts auxiliary infrastructure services only (DB, Redis, etc.) for host-local development |
| `dev` | `make up` | Builds and runs the application container with development mounts and hot-reload |
| `prod` | `make up-prod` | Builds and runs the hardened, non-root production target image |
