from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reminder_preferences_have_safe_defaults_and_bounds():
    entities = (ROOT / "app" / "models" / "entities.py").read_text()
    schemas = (ROOT / "app" / "schemas" / "documents.py").read_text()
    assert "reminders_enabled: Mapped[bool]" in entities and "default=True" in entities
    assert "reminder_window_days: Mapped[int]" in entities and "default=90" in entities
    assert "window_days: int = Field(ge=1, le=3650)" in schemas


def test_reminder_preferences_migration_is_sequential_and_fresh_install_safe():
    migration = (ROOT / "alembic" / "versions" / "0010_reminder_preferences.py").read_text()
    assert 'down_revision = "0009"' in migration
    assert 'get_columns("users")' in migration
    assert 'if "reminders_enabled" not in columns' in migration
    assert 'if "reminder_window_days" not in columns' in migration


def test_reminder_preferences_are_owner_derived_and_control_listing():
    source = (ROOT / "app" / "api" / "documents.py").read_text()
    assert '@router.get("/reminders/preferences"' in source
    assert '@router.put("/reminders/preferences"' in source
    assert "user.reminders_enabled = payload.enabled" in source
    assert "user.reminder_window_days = payload.window_days" in source
    assert "if not user.reminders_enabled" in source
