import os
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Allow the GA0 webpage to access our API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULTS = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

KNOWN_KEYS = set(DEFAULTS)


def parse_env_file(path):
    """Read a .env file without changing the real OS environment."""
    result = {}

    if not path.exists():
        return result

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")

    return result


def normalize_key(key):
    """Convert configuration names into standard application keys."""
    key = key.strip()

    if key.upper() == "NUM_WORKERS":
        return "workers"

    if key.upper().startswith("APP_"):
        key = key[4:]

    key = key.lower()

    if key == "num_workers":
        return "workers"

    return key


def convert_value(key, value):
    """Convert values to the correct data types."""
    if key in ("port", "workers"):
        return int(value)

    if key == "debug":
        if isinstance(value, bool):
            return value

        return str(value).strip().lower() in {
            "true", "1", "yes", "on"
        }

    return str(value)


def apply_layer(config, values):
    """Apply a configuration layer over the existing configuration."""
    for original_key, value in values.items():
        key = normalize_key(original_key)

        if key in KNOWN_KEYS:
            config[key] = value


@app.get("/")
async def home():
    return {"message": "Configuration API is running"}


@app.get("/effective-config")
async def effective_config(request: Request):
    config = DEFAULTS.copy()

    # Layer 1: defaults are already applied.

    # Layer 2: environment-specific YAML configuration.
    environment = os.environ.get("APP_ENV", "development")
    yaml_path = Path(f"config.{environment}.yaml")

    if yaml_path.exists():
        yaml_data = yaml.safe_load(
            yaml_path.read_text(encoding="utf-8")
        ) or {}

        apply_layer(config, yaml_data)

    # Layer 3: .env file.
    env_file_values = parse_env_file(Path(".env"))
    apply_layer(config, env_file_values)

    # Layer 4: operating-system environment variables.
    os_values = {
        key: value
        for key, value in os.environ.items()
        if key.upper().startswith("APP_")
    }
    apply_layer(config, os_values)

    # Highest precedence: query parameters such as set-port=9000.
    for parameter, value in request.query_params.multi_items():
        if parameter.startswith("set-"):
            key = normalize_key(parameter[4:])

            if key in KNOWN_KEYS:
                config[key] = value

    # Convert values after all layers have been merged.
    result = {
        key: convert_value(key, value)
        for key, value in config.items()
    }

    # Never expose the real API key.
    result["api_key"] = "****"

    return result