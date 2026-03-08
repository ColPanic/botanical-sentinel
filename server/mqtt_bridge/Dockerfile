FROM python:3.13-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml .
RUN uv pip install --system --no-cache .
COPY src/ src/
CMD ["python", "-m", "mqtt_bridge"]
