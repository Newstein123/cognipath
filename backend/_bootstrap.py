"""Make the entry points work without activating the virtualenv first.

Every dependency lives in .venv, so `python3 app.py` from a shell that has not activated
it dies on `from google import genai` with an ImportError traceback — which tells a user
nothing about what to do. This module is imported first by each entry point and either
fixes the problem or explains it.

Two behaviours, in order:

1. If the dependencies are missing and .venv holds a working interpreter, re-exec into it.
   The command the user typed then simply works. A one-line notice says what happened, so
   it is visible rather than magic.

2. If there is no usable .venv, print the setup steps and stop. A traceback from inside
   google.genai is not a setup instruction.

Guarded by an environment variable so a broken .venv cannot cause an exec loop.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_GUARD = "COGNITH_BOOTSTRAPPED"
_ROOT = Path(__file__).resolve().parent
_VENV_PYTHON = _ROOT / ".venv" / "bin" / "python"

#: Third-party packages the project cannot run without, and why, for the error message.
_REQUIRED = [
    ("google.genai", "google-genai"),
    ("numpy", "numpy"),
    ("yaml", "pyyaml"),
    ("pydantic", "pydantic"),
    ("dotenv", "python-dotenv"),
]


def _missing() -> list[str]:
    import importlib.util

    out = []
    for module, package in _REQUIRED:
        try:
            if importlib.util.find_spec(module) is None:
                out.append(package)
        except (ImportError, ValueError):
            out.append(package)
    return out


def ensure_dependencies() -> None:
    missing = _missing()
    if not missing:
        return

    already_tried = os.environ.get(_GUARD) == "1"
    running_venv = Path(sys.executable).resolve() == _VENV_PYTHON.resolve() \
        if _VENV_PYTHON.exists() else False

    if _VENV_PYTHON.exists() and not already_tried and not running_venv:
        print(f"  (using {_VENV_PYTHON.relative_to(_ROOT)} — the dependencies live there)",
              file=sys.stderr)
        os.environ[_GUARD] = "1"
        os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON), *sys.argv])

    print(
        "\n  Cognith cannot start — these packages are not available:\n"
        f"      {', '.join(missing)}\n\n"
        "  Set it up with:\n\n"
        "      python3 -m venv .venv\n"
        "      source .venv/bin/activate\n"
        "      pip install -r requirements.txt\n\n"
        "  Then run it again. If .venv already exists, activating it is enough:\n\n"
        "      source .venv/bin/activate\n",
        file=sys.stderr,
    )
    raise SystemExit(1)


ensure_dependencies()
