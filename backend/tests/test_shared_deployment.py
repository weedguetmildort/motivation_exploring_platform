import pytest
from scripts.research_deployment import validate_shared_config, shared_preflight, shared_smoke, DeploymentError


def configuration():
    """Every variable set, as a fully configured backend app would have them."""
    return dict(MONGO_URL="mongodb+srv://database.example/test", MONGO_DB="existing_experiment",
        JWT_SECRET="s" * 40, COOKIE_NAME="session", COOKIE_SECURE="true", COOKIE_SAMESITE="Lax",
        FRONTEND_ORIGIN="https://shared-front.example", ENV="production", UF_OPENAI_API_KEY="test",
        UF_OPENAI_BASE_URL="https://ai.example/v1", UF_OPENAI_API_MODEL="test-model",
        STUDY_ACCESS_MODE="independent_approval")


def minimal_configuration():
    """Only what the backend cannot run in production without."""
    return dict(MONGO_URL="mongodb+srv://database.example/test", MONGO_DB="existing_experiment",
        JWT_SECRET="s" * 40, COOKIE_SECURE="true", UF_OPENAI_API_KEY="test",
        UF_OPENAI_BASE_URL="https://ai.example/v1", STUDY_ACCESS_MODE="independent_approval")


def test_shared_config_keeps_existing_database_and_cookie():
    validate_shared_config(configuration())


def test_variables_with_working_app_defaults_are_optional():
    # COOKIE_NAME, COOKIE_SAMESITE, UF_OPENAI_API_MODEL default in app/core;
    # ENV is never read; FRONTEND_ORIGIN is unused behind the frontend proxy.
    validate_shared_config(minimal_configuration())


@pytest.mark.parametrize("field", ["MONGO_URL", "MONGO_DB", "JWT_SECRET", "COOKIE_SECURE",
                                   "UF_OPENAI_API_KEY", "UF_OPENAI_BASE_URL", "STUDY_ACCESS_MODE"])
def test_variables_without_a_working_default_are_required(field):
    config = minimal_configuration(); del config[field]
    with pytest.raises(DeploymentError, match=f"Missing shared backend config vars: {field}"):
        validate_shared_config(config)


def test_blank_values_count_as_missing():
    with pytest.raises(DeploymentError, match="JWT_SECRET"):
        validate_shared_config({**minimal_configuration(), "JWT_SECRET": "   "})


@pytest.mark.parametrize("field,value", [("JWT_SECRET", "short"), ("JWT_SECRET", "dev-secret-change-me"),
    ("COOKIE_DOMAIN", ".example.com"), ("COOKIE_SECURE", "false"), ("COOKIE_SAMESITE", "None"),
    ("MONGO_URL", "https://example.com"), ("UF_OPENAI_BASE_URL", "http://ai.example/v1"),
    ("STUDY_ACCESS_MODE", "approval"), ("STUDY_ACCESS_MODE", "")])
def test_rejects_invalid_shared_configuration(field, value):
    config = configuration(); config[field] = value
    with pytest.raises(DeploymentError):
        validate_shared_config(config)


@pytest.mark.parametrize("field,value", [("ENV", "development"), ("FRONTEND_ORIGIN", "http://front.example"),
    ("FRONTEND_ORIGIN", "https://front.example/app")])
def test_optional_variables_are_still_checked_when_set(field, value):
    with pytest.raises(DeploymentError):
        validate_shared_config({**minimal_configuration(), field: value})


@pytest.mark.parametrize("origin", ["https://shared-front.example", "https://study.example.edu/"])
def test_frontend_origin_may_be_the_heroku_url_or_a_custom_domain(origin):
    validate_shared_config({**minimal_configuration(), "FRONTEND_ORIGIN": origin})


def test_study_access_mode_must_be_set_explicitly():
    config = configuration(); del config["STUDY_ACCESS_MODE"]
    with pytest.raises(DeploymentError, match="STUDY_ACCESS_MODE"):
        validate_shared_config(config)


@pytest.mark.parametrize("mode", ["sequential_approval", "sequential", "independent_approval", "independent", " Independent "])
def test_every_mode_the_backend_accepts_passes(mode):
    from app.core.config import STUDY_ACCESS_MODES
    from scripts.research_deployment import STUDY_ACCESS_MODES as checked
    assert set(checked) == set(STUDY_ACCESS_MODES)
    validate_shared_config({**configuration(), "STUDY_ACCESS_MODE": mode})


def run_preflight(monkeypatch, tmp_path, config=None):
    from scripts import research_deployment as deployment
    monkeypatch.setenv("APP_BACKEND", "shared-backend")
    monkeypatch.setenv("APP_FRONTEND", "shared-frontend")
    monkeypatch.setenv("HEROKU_API_KEY", "test")
    output = tmp_path / "output"; monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    paths = []
    def get(path, token):
        paths.append(path)
        if path.endswith("/config-vars"):
            return config or configuration()
        return {"stack": {"name": "container"}, "web_url": "https://shared-front.example/" if path.endswith("shared-frontend") else "https://shared-back.example/"}
    monkeypatch.setattr(deployment, "heroku_get", get)
    shared_preflight()
    return paths, output.read_text()


def test_preflight_uses_actual_urls_and_only_two_apps(monkeypatch, tmp_path):
    monkeypatch.delenv("BACKEND_URL", raising=False)
    paths, output = run_preflight(monkeypatch, tmp_path)
    assert paths == ["/apps/shared-backend", "/apps/shared-frontend", "/apps/shared-backend/config-vars"]
    assert output.splitlines() == ["backend_url=https://shared-back.example", "frontend_url=https://shared-front.example"]


def test_preflight_passes_with_only_the_required_variables(monkeypatch, tmp_path):
    monkeypatch.delenv("BACKEND_URL", raising=False)
    run_preflight(monkeypatch, tmp_path, minimal_configuration())


@pytest.mark.parametrize("secret,expected", [
    ("api.study.example.edu", "https://api.study.example.edu"),   # bare host, as the old workflow stored it
    ("https://api.study.example.edu/", "https://api.study.example.edu"),
    ("  ", "https://shared-back.example"),                        # empty secret falls back to Heroku's URL
])
def test_the_backend_url_secret_is_preferred_when_set(monkeypatch, tmp_path, secret, expected):
    monkeypatch.setenv("BACKEND_URL", secret)
    _, output = run_preflight(monkeypatch, tmp_path)
    assert output.splitlines()[0] == f"backend_url={expected}"


@pytest.mark.parametrize("secret", ["http://api.study.example.edu", "https://api.study.example.edu/v1"])
def test_an_unusable_backend_url_secret_stops_the_deploy(monkeypatch, tmp_path, secret):
    monkeypatch.setenv("BACKEND_URL", secret)
    with pytest.raises(DeploymentError):
        run_preflight(monkeypatch, tmp_path)


def test_smoke_checks_study2_and_approval_routes_without_logging_in(monkeypatch):
    from scripts import research_deployment as deployment
    monkeypatch.setenv("FRONTEND_URL", "https://shared-front.example")
    monkeypatch.setattr(deployment, "smoke", lambda: None)
    checks = []; monkeypatch.setattr(deployment, "probe", lambda *args: checks.append(args))
    shared_smoke()
    assert len(checks) == 3 and all(status == 401 for _, status, _ in checks)
    assert any("study-2/study/next" in url for url, _, _ in checks)
