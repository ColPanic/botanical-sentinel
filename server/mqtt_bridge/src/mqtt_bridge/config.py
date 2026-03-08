import os


def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f"Required environment variable {key!r} is not set")
    return val


MQTT_HOST: str = _require("MQTT_HOST")
MQTT_PORT: int = int(os.environ.get("MQTT_PORT", "1883"))
DB_URL: str = _require("DB_URL")
