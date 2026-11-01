"""Load API keys from the repo's .env file into os.environ (stdlib only, no python-dotenv).

Variables already set in the shell win, and empty values are skipped so a blank key leaves that
LLM hypothesizer off.
"""
import os
import pathlib

ENV_FILE = pathlib.Path(__file__).resolve().parent.parent / ".env"


def load_env(path=ENV_FILE) -> list:
    """Set KEY=value pairs from `path` that are not already in the environment; return the keys set."""
    path = pathlib.Path(path)
    if not path.is_file():
        return []
    loaded = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("'\"")
        if value and not os.environ.get(key):
            os.environ[key] = value
            loaded.append(key)
    return loaded
