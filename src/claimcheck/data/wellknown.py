"""Curated lists of well-known public packages.

These ground the "legitimately public, ignore" class so the tool does not
false-positive on ``requests`` or ``lodash``. The lists are intentionally small
and high-signal (widely-used top packages); they are *not* an exhaustive mirror
of the registries. The live registry probe (Tier 2) is what authoritatively
decides existence — this list only helps the classifier skip obvious externals
without a lookup.

Names are stored canonicalized (PEP 503 for PyPI, lowercase for npm).
"""

from __future__ import annotations

# Top PyPI packages (canonicalized).
WELLKNOWN_PYPI: frozenset[str] = frozenset(
    {
        "requests", "urllib3", "setuptools", "pip", "wheel", "numpy", "pandas",
        "boto3", "botocore", "certifi", "idna", "charset-normalizer", "six",
        "python-dateutil", "pyyaml", "flask", "django", "fastapi", "starlette",
        "pydantic", "sqlalchemy", "click", "jinja2", "markupsafe", "werkzeug",
        "pytest", "pytest-cov", "tox", "coverage", "scipy", "scikit-learn",
        "matplotlib", "pillow", "cryptography", "cffi", "pycparser", "attrs",
        "packaging", "typing-extensions", "aiohttp", "httpx", "redis",
        "celery", "gunicorn", "uvicorn", "tenacity", "rich", "tqdm",
        "beautifulsoup4", "lxml", "openpyxl", "protobuf", "grpcio",
    }
)

# Top npm packages (canonicalized, scope preserved where applicable).
WELLKNOWN_NPM: frozenset[str] = frozenset(
    {
        "lodash", "react", "react-dom", "express", "chalk", "commander",
        "axios", "debug", "typescript", "webpack", "babel-core", "eslint",
        "prettier", "jest", "mocha", "chai", "vue", "angular", "rxjs",
        "moment", "dayjs", "uuid", "dotenv", "cors", "body-parser", "next",
        "@babel/core", "@babel/preset-env", "@types/node", "@types/react",
        "@angular/core", "@vue/cli", "semver", "glob", "minimatch", "yargs",
        "inquirer", "ws", "socket.io", "mongoose", "pg", "mysql2", "redis",
        "jsonwebtoken", "bcrypt", "nodemon", "ts-node", "rollup", "vite",
    }
)


def is_wellknown(normalized: str, ecosystem: str) -> bool:
    if ecosystem == "pypi":
        return normalized in WELLKNOWN_PYPI
    if ecosystem == "npm":
        return normalized in WELLKNOWN_NPM
    return False
