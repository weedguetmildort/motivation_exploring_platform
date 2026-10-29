"""Read-only preflight and post-release checks for the shared two-study app.

Legacy separate-study validators are retained for compatibility; the single CD
workflow uses shared-preflight/shared-smoke and deploys only two apps.

Uses only Python's standard library so it can run directly on an Actions runner.
Never print config dictionaries, API credentials, or private API response bodies.
"""
import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class DeploymentError(ValueError):
    pass


def require_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise DeploymentError(f"Missing GitHub secret/environment variable: {name}")
    return value


def validate_targets(backend, frontend, existing_backend, existing_frontend):
    names = (backend, frontend, existing_backend, existing_frontend)
    if any(not re.fullmatch(r"[a-z][a-z0-9-]{1,29}", name) for name in names):
        raise DeploymentError("Use Heroku app names, not URLs, in the app-name secrets")
    if backend == frontend:
        raise DeploymentError("The research frontend and backend must be different apps")
    if {backend, frontend} & {existing_backend, existing_frontend}:
        raise DeploymentError("Research targets must not reuse either existing experiment app")


def public_origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise DeploymentError("App URLs must be HTTPS origins without paths or credentials")
    return value.rstrip("/")


def validate_config(config, existing, frontend_url):
    required = ("MONGO_URL", "MONGO_DB", "JWT_SECRET", "COOKIE_NAME", "COOKIE_SECURE",
                "COOKIE_SAMESITE", "FRONTEND_ORIGIN", "ENV", "UF_OPENAI_API_KEY",
                "UF_OPENAI_BASE_URL", "UF_OPENAI_API_MODEL")
    missing = [name for name in required if not str(config.get(name) or "").strip()]
    if missing:
        raise DeploymentError("Missing research backend config vars: " + ", ".join(missing))
    if config["MONGO_DB"] in {existing.get("MONGO_DB") or "mep_dev", "mep_dev"}:
        raise DeploymentError("MONGO_DB must name a separate research database")
    if not config["MONGO_URL"].startswith(("mongodb://", "mongodb+srv://")):
        raise DeploymentError("MONGO_URL must be a MongoDB connection string")
    secret = config["JWT_SECRET"]
    if len(secret) < 32 or secret == existing.get("JWT_SECRET") or secret == "dev-secret-change-me":
        raise DeploymentError("JWT_SECRET must be a fresh random secret of at least 32 characters")
    if config["COOKIE_NAME"] == (existing.get("COOKIE_NAME") or "session"):
        raise DeploymentError("Use a different COOKIE_NAME for the research study")
    if config["COOKIE_SECURE"].lower() not in {"true", "1", "yes"}:
        raise DeploymentError("Set COOKIE_SECURE=true on the research backend")
    if config.get("COOKIE_DOMAIN"):
        raise DeploymentError("Remove COOKIE_DOMAIN: use host-only cookies through the frontend proxy")
    if config["COOKIE_SAMESITE"].lower() != "lax":
        raise DeploymentError("Set COOKIE_SAMESITE=Lax for same-origin frontend proxy requests")
    if config["ENV"] != "production":
        raise DeploymentError("Set ENV=production on the research backend")
    if public_origin(config["FRONTEND_ORIGIN"]) != frontend_url:
        raise DeploymentError("FRONTEND_ORIGIN must match the new frontend's actual Heroku URL")
    ai_url = urlsplit(config["UF_OPENAI_BASE_URL"])
    if ai_url.scheme != "https" or not ai_url.hostname or ai_url.username or ai_url.password:
        raise DeploymentError("UF_OPENAI_BASE_URL must be an accessible HTTPS API endpoint")


def heroku_get(path, token):
    request = Request("https://api.heroku.com" + path, headers={
        "Accept": "application/vnd.heroku+json; version=3",
        "Authorization": "Bearer " + token,
        "User-Agent": "mep-research-deployment",
    })
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def preflight():
    backend = require_env("RESEARCH_BACKEND_APP")
    frontend = require_env("RESEARCH_FRONTEND_APP")
    original_backend = require_env("EXISTING_BACKEND_APP")
    original_frontend = require_env("EXISTING_FRONTEND_APP")
    validate_targets(backend, frontend, original_backend, original_frontend)
    token = require_env("HEROKU_API_KEY")
    backend_info = heroku_get(f"/apps/{backend}", token)
    frontend_info = heroku_get(f"/apps/{frontend}", token)
    for info in (backend_info, frontend_info):
        if info.get("stack", {}).get("name") != "container":
            raise DeploymentError("Create both new apps on the Cedar container stack")
    backend_url = public_origin(backend_info["web_url"])
    frontend_url = public_origin(frontend_info["web_url"])
    if backend_url == frontend_url:
        raise DeploymentError("Frontend and backend URLs must be different")
    config = heroku_get(f"/apps/{backend}/config-vars", token)
    existing = heroku_get(f"/apps/{original_backend}/config-vars", token)
    validate_config(config, existing, frontend_url)
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"backend_url={backend_url}\nfrontend_url={frontend_url}\n")
    print(f"Research preflight passed. Frontend: {frontend_url}; backend: {backend_url}")


def probe(url, expected_status, expected_json=None):
    try:
        response = urlopen(Request(url, headers={"Accept": "application/json"}), timeout=15)
    except HTTPError as error:
        response = error
    with response:
        if response.status != expected_status:
            raise DeploymentError(f"{url}: expected HTTP {expected_status}, received {response.status}")
        if expected_json is not None and json.load(response) != expected_json:
            raise DeploymentError(f"{url}: unexpected response body")


def smoke():
    backend = public_origin(require_env("BACKEND_URL"))
    frontend = public_origin(require_env("FRONTEND_URL"))
    checks = (
        (backend + "/health", 200, {"status": "ok"}),
        (frontend + "/api/health", 200, {"status": "ok"}),
        # With no cookie, 401 is correct; 404 means the flow route/proxy is missing.
        (frontend + "/api/study/next", 401, {"detail": "Not authenticated"}),
        (frontend + "/auth/me", 401, {"detail": "Not authenticated"}),
        (frontend + "/", 200, None),
    )
    for attempt in range(18):
        try:
            for check in checks:
                probe(*check)
            print("Research health, authentication, and study-route checks passed")
            return
        except (DeploymentError, URLError, TimeoutError, json.JSONDecodeError):
            if attempt == 17:
                raise
            time.sleep(5)


# Mirrors app.core.config.STUDY_ACCESS_MODES; this script stays standard-library only.
STUDY_ACCESS_MODES = ("sequential_approval", "sequential", "independent_approval", "independent")


def validate_shared_config(config, frontend_url):
    required = ("MONGO_URL", "MONGO_DB", "JWT_SECRET", "COOKIE_NAME", "COOKIE_SECURE",
                "COOKIE_SAMESITE", "FRONTEND_ORIGIN", "ENV", "UF_OPENAI_API_KEY",
                "UF_OPENAI_BASE_URL", "UF_OPENAI_API_MODEL", "STUDY_ACCESS_MODE")
    missing = [key for key in required if not str(config.get(key) or "").strip()]
    if missing:
        raise DeploymentError("Missing shared backend config vars: " + ", ".join(missing))
    # An unknown mode stops the backend from starting; who may enter Study 2 is set explicitly.
    if config["STUDY_ACCESS_MODE"].strip().lower() not in STUDY_ACCESS_MODES:
        raise DeploymentError("STUDY_ACCESS_MODE must be one of: " + ", ".join(STUDY_ACCESS_MODES))
    if not config["MONGO_URL"].startswith(("mongodb://", "mongodb+srv://")):
        raise DeploymentError("MONGO_URL must be a MongoDB connection string")
    if len(config["JWT_SECRET"]) < 32 or config["JWT_SECRET"] == "dev-secret-change-me":
        raise DeploymentError("Use a JWT_SECRET of at least 32 characters")
    if config["COOKIE_SECURE"].lower() not in ("1", "true", "yes") or config["COOKIE_SAMESITE"].lower() != "lax":
        raise DeploymentError("Use secure host-only cookies with COOKIE_SAMESITE=Lax")
    if config.get("COOKIE_DOMAIN") or config["ENV"] != "production":
        raise DeploymentError("Use ENV=production and omit COOKIE_DOMAIN")
    if public_origin(config["FRONTEND_ORIGIN"]) != frontend_url:
        raise DeploymentError("FRONTEND_ORIGIN must match the shared frontend")
    endpoint = urlsplit(config["UF_OPENAI_BASE_URL"])
    if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password:
        raise DeploymentError("UF_OPENAI_BASE_URL must be an HTTPS API endpoint")


def shared_preflight():
    backend, frontend = require_env("APP_BACKEND"), require_env("APP_FRONTEND")
    if backend == frontend or any(not re.fullmatch(r"[a-z][a-z0-9-]{1,29}", name) for name in (backend, frontend)):
        raise DeploymentError("Supply two distinct Heroku app names for the shared frontend and backend")
    token = require_env("HEROKU_API_KEY")
    back, front = heroku_get(f"/apps/{backend}", token), heroku_get(f"/apps/{frontend}", token)
    if any(info.get("stack", {}).get("name") != "container" for info in (back, front)):
        raise DeploymentError("Both shared apps must use the container stack")
    backend_url, frontend_url = public_origin(back["web_url"]), public_origin(front["web_url"])
    validate_shared_config(heroku_get(f"/apps/{backend}/config-vars", token), frontend_url)
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"backend_url={backend_url}\nfrontend_url={frontend_url}\n")
    print(f"Shared study preflight passed. Frontend: {frontend_url}; backend: {backend_url}")


def shared_smoke():
    smoke()
    frontend = public_origin(require_env("FRONTEND_URL"))
    for route in ("/api/studies/catalog", "/api/studies/study-2/study/next", "/api/studies/participants"):
        probe(frontend + route, 401, {"detail": "Not authenticated"})
    print("Shared Study 1, Study 2, and interview approval routing passed")


def main():
    try:
        if sys.argv[1:] == ["shared-preflight"]:
            shared_preflight()
        elif sys.argv[1:] == ["shared-smoke"]:
            shared_smoke()
        elif sys.argv[1:] == ["preflight"]:
            preflight()
        elif sys.argv[1:] == ["smoke"]:
            smoke()
        else:
            raise DeploymentError("Usage: research_deployment.py shared-preflight|shared-smoke")
    except HTTPError as error:
        print(f"Heroku API returned HTTP {error.code}; check app access and the research API key", file=sys.stderr)
        return 1
    except (DeploymentError, URLError, TimeoutError, KeyError, json.JSONDecodeError) as error:
        # Do not include exception text from network/config parsing: it may
        # contain private response data. Validation messages contain names only.
        message = str(error) if isinstance(error, DeploymentError) else type(error).__name__
        print(f"Research deployment check failed: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
