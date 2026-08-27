"""Unit tests for the .env fallback reader."""

from engines.walk.lib.env import read_var


def test_environment_wins_over_the_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("INVENTED_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("INVENTED_KEY", "from-environment")
    assert read_var("INVENTED_KEY", env_file) == "from-environment"


def test_file_supplies_an_unset_variable(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("# a comment\n\nINVENTED_KEY=from-file\n",
                        encoding="utf-8")
    monkeypatch.delenv("INVENTED_KEY", raising=False)
    assert read_var("INVENTED_KEY", env_file) == "from-file"


def test_quotes_around_the_value_are_stripped(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('INVENTED_KEY="quoted value"\n', encoding="utf-8")
    monkeypatch.delenv("INVENTED_KEY", raising=False)
    assert read_var("INVENTED_KEY", env_file) == "quoted value"


def test_absent_everywhere_is_none(tmp_path, monkeypatch):
    monkeypatch.delenv("INVENTED_KEY", raising=False)
    assert read_var("INVENTED_KEY", tmp_path / "absent.env") is None


def test_an_empty_assignment_is_absent(tmp_path, monkeypatch):
    # The .env template ships with "MISTRAL_API_KEY=" awaiting a value; an
    # empty assignment must read as unset, not as an empty key.
    env_file = tmp_path / ".env"
    env_file.write_text("INVENTED_KEY=\n", encoding="utf-8")
    monkeypatch.delenv("INVENTED_KEY", raising=False)
    assert read_var("INVENTED_KEY", env_file) is None
