import pytest
from scripts.research_deployment import validate_shared_config, shared_preflight, shared_smoke, DeploymentError


def configuration():
    return dict(MONGO_URL="mongodb+srv://database.example/test", MONGO_DB="existing_experiment",
        JWT_SECRET="s" * 40, COOKIE_NAME="session", COOKIE_SECURE="true", COOKIE_SAMESITE="Lax",
        FRONTEND_ORIGIN="https://shared-front.example", ENV="production", UF_OPENAI_API_KEY="test",
        UF_OPENAI_BASE_URL="https://ai.example/v1", UF_OPENAI_API_MODEL="test-model",
        STUDY_ACCESS_MODE="independent_approval")


def test_shared_config_keeps_existing_database_and_cookie():
    validate_shared_config(configuration(), "https://shared-front.example")


@pytest.mark.parametrize("field,value", [("JWT_SECRET", "short"), ("COOKIE_DOMAIN", ".example.com"),
    ("COOKIE_SECURE", "false"), ("FRONTEND_ORIGIN", "https://other.example"), ("MONGO_URL", "https://example.com"),
    ("STUDY_ACCESS_MODE", "approval"), ("STUDY_ACCESS_MODE", "")])
def test_rejects_invalid_shared_configuration(field, value):
    config = configuration(); config[field] = value
    with pytest.raises(DeploymentError):
        validate_shared_config(config, "https://shared-front.example")


def test_study_access_mode_must_be_set_explicitly():
    config = configuration(); del config["STUDY_ACCESS_MODE"]
    with pytest.raises(DeploymentError, match="STUDY_ACCESS_MODE"):
        validate_shared_config(config, "https://shared-front.example")


@pytest.mark.parametrize("mode", ["sequential_approval", "sequential", "independent_approval", "independent", " Independent "])
def test_every_mode_the_backend_accepts_passes(mode):
    from app.core.config import STUDY_ACCESS_MODES
    from scripts.research_deployment import STUDY_ACCESS_MODES as checked
    assert set(checked) == set(STUDY_ACCESS_MODES)
    validate_shared_config({**configuration(), "STUDY_ACCESS_MODE": mode}, "https://shared-front.example")


def test_preflight_uses_actual_urls_and_only_two_apps(monkeypatch, tmp_path):
    from scripts import research_deployment as deployment
    monkeypatch.setenv("APP_BACKEND", "shared-backend")
    monkeypatch.setenv("APP_FRONTEND", "shared-frontend")
    monkeypatch.setenv("HEROKU_API_KEY", "test")
    output = tmp_path / "output"; monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    paths = []
    def get(path, token):
        paths.append(path)
        if path.endswith("/config-vars"):
            return configuration()
        return {"stack": {"name": "container"}, "web_url": "https://shared-front.example" if path.endswith("shared-frontend") else "https://shared-back.example"}
    monkeypatch.setattr(deployment, "heroku_get", get)
    shared_preflight()
    assert paths == ["/apps/shared-backend", "/apps/shared-frontend", "/apps/shared-backend/config-vars"]
    assert "backend_url=https://shared-back.example" in output.read_text()


def test_smoke_checks_study2_and_approval_routes_without_logging_in(monkeypatch):
    from scripts import research_deployment as deployment
    monkeypatch.setenv("FRONTEND_URL", "https://shared-front.example")
    monkeypatch.setattr(deployment, "smoke", lambda: None)
    checks = []; monkeypatch.setattr(deployment, "probe", lambda *args: checks.append(args))
    shared_smoke()
    assert len(checks) == 3 and all(status == 401 for _, status, _ in checks)
    assert any("study-2/study/next" in url for url, _, _ in checks)
