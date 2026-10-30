"""Read KEY=VALUE lines from the git-ignored .env file into the environment.

Values already in the environment win, so CI or a shell export can override the file. It returns
the names it set, never the values, so nothing here can print a key.
"""

import os
from pathlib import Path


def load_env_file(path: Path = Path(".env")) -> list[str]:
    if not path.exists():
        return []
    loaded = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = (part.strip() for part in line.split("=", 1))
        if name and name not in os.environ:
            os.environ[name] = value
            loaded.append(name)
    return loaded
