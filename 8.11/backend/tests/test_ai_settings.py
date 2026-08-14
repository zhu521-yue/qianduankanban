from types import SimpleNamespace

import app.services as services_module
import app.settings as settings_module
from app.schemas import UserContext
from app.services import SettingsService
from app.settings import ai_settings_for_role, save_ai_settings_for_role


def test_role_ai_settings_are_isolated(monkeypatch) -> None:
    fake = SimpleNamespace(
        ai_manager_base_url="https://manager.example/v1",
        ai_manager_api_key="manager-key",
        ai_manager_model_name="manager-model",
        ai_talent_base_url="https://talent.example/v1",
        ai_talent_api_key="talent-key",
        ai_talent_model_name="talent-model",
        ai_private_base_url="https://private.example/v1",
        ai_private_api_key="private-key",
        ai_private_model_name="private-model",
        ai_distribution_base_url="https://distribution.example/v1",
        ai_distribution_api_key="distribution-key",
        ai_distribution_model_name="distribution-model",
        ai_base_url="",
        ai_api_key="",
        ai_model_name="",
    )
    monkeypatch.setattr(settings_module, "get_settings", lambda: fake)

    assert ai_settings_for_role("manager")["api_key"] == "manager-key"
    assert ai_settings_for_role("talent")["api_key"] == "talent-key"
    assert ai_settings_for_role("private")["api_key"] == "private-key"
    assert ai_settings_for_role("distribution")["api_key"] == "distribution-key"


def test_saving_one_role_preserves_other_env_values(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://example\n"
        "AI_MANAGER_API_KEY=old-manager\n"
        "AI_TALENT_API_KEY=talent-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "ENV_FILE", env_file)

    save_ai_settings_for_role("manager", "https://manager.example/v1/", "new-manager", "manager-model")

    saved = env_file.read_text(encoding="utf-8")
    assert "DATABASE_URL=postgresql://example" in saved
    assert 'AI_MANAGER_BASE_URL="https://manager.example/v1"' in saved
    assert 'AI_MANAGER_API_KEY="new-manager"' in saved
    assert 'AI_MANAGER_MODEL_NAME="manager-model"' in saved
    assert "AI_TALENT_API_KEY=talent-secret" in saved


def test_service_uses_current_login_role_and_masks_secret(monkeypatch) -> None:
    requested_roles: list[str] = []

    def fake_role_config(role: str) -> dict[str, str]:
        requested_roles.append(role)
        return {"base_url": f"https://{role}.example/v1", "api_key": f"{role}-secret", "model_name": f"{role}-model"}

    monkeypatch.setattr(services_module, "ai_settings_for_role", fake_role_config)
    service = SettingsService(None)  # type: ignore[arg-type]
    user = UserContext("talent-user", "talent", "达人组长", "talent", "talent")

    public = service.api_setting(user)
    private = service.api_setting(user, include_secret=True)

    assert requested_roles == ["talent", "talent"]
    assert public["api_key_masked"] == "••••••••"
    assert "api_key" not in public
    assert private["api_key"] == "talent-secret"


def test_existing_secret_is_reused_when_password_field_is_blank(monkeypatch) -> None:
    service = SettingsService(None)  # type: ignore[arg-type]
    user = UserContext("private-user", "private", "私域组长", "private", "private")
    monkeypatch.setattr(
        service,
        "api_setting",
        lambda _user, include_secret=False: {
            "base_url": "https://old.example/v1",
            "model_name": "old-model",
            "api_key": "stored-secret" if include_secret else "",
        },
    )
    monkeypatch.setattr(services_module, "get_settings", lambda: SimpleNamespace(ai_default_model="default"))

    resolved = service.resolve_api_setting(user, "https://new.example/v1/", None, "new-model")

    assert resolved == {
        "base_url": "https://new.example/v1",
        "api_key": "stored-secret",
        "model_name": "new-model",
    }
