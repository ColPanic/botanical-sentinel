FROM python:3.13-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN uv pip install --system --no-cache .
CMD ["python", "-m", "mqtt_bridge"]
