FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip && rm -rf /var/lib/apt/lists/* \
  && useradd --create-home --shell /bin/bash mluser
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
USER mluser
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python3 -m {{PACKAGE_NAME}}.device
CMD ["python3", "-m", "{{PACKAGE_NAME}}.device"]
