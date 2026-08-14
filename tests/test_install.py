"""Tests for the installer, run against a temporary HOME.

The installer writes outside the repository, so every test here points
HOME at tmp_path and passes --links-only: the venv is somebody else's
concern and building one would need the network. What is checked is the
part that touches a stranger's machine, which is the settings file it
amends and the links it refuses to overwrite.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL = REPO_ROOT / "tools" / "install.sh"

LINKS = ("skills/alteksto", "agents/prepare-paper.md", "agents/sweep-paper.md")


def install(home, *args):
    """Run the installer with HOME redirected, returning the completed run."""
    return subprocess.run(
        ["bash", str(INSTALL), "--links-only", *args],
        capture_output=True, text=True, env={"HOME": str(home), "PATH":
                                             "/usr/bin:/bin:/usr/local/bin"})


def settings_of(home):
    return json.loads((home / ".claude" / "settings.json").read_text())


def test_links_and_home_are_registered(tmp_path):
    result = install(tmp_path)

    assert result.returncode == 0, result.stderr
    for name in LINKS:
        link = tmp_path / ".claude" / name
        assert link.is_symlink()
        assert link.resolve().exists()
    assert settings_of(tmp_path)["env"]["ALTEKSTO_HOME"] == str(REPO_ROOT)


def test_dry_run_changes_nothing(tmp_path):
    result = install(tmp_path, "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "would" in result.stdout
    assert not (tmp_path / ".claude").exists()


def test_running_twice_is_the_same_as_once(tmp_path):
    assert install(tmp_path).returncode == 0

    result = install(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "already" in result.stdout
    assert settings_of(tmp_path)["env"]["ALTEKSTO_HOME"] == str(REPO_ROOT)


def test_existing_settings_keys_survive(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text(json.dumps(
        {"model": "opus", "env": {"OTHER": "kept"}}), encoding="utf-8")

    assert install(tmp_path).returncode == 0

    settings = settings_of(tmp_path)
    assert settings["model"] == "opus"
    assert settings["env"]["OTHER"] == "kept"
    assert settings["env"]["ALTEKSTO_HOME"] == str(REPO_ROOT)
    assert (claude / "settings.json.bak").is_file()


def test_a_settings_file_that_is_not_json_stops_the_install(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text("{ not json", encoding="utf-8")

    result = install(tmp_path)

    assert result.returncode != 0
    assert "not valid JSON" in result.stdout + result.stderr
    assert (claude / "settings.json").read_text() == "{ not json"


def test_a_real_file_in_the_way_is_never_removed(tmp_path):
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "prepare-paper.md").write_text("mine", encoding="utf-8")

    result = install(tmp_path)

    assert result.returncode != 0
    assert "REFUSING" in result.stdout
    assert (agents / "prepare-paper.md").read_text() == "mine"


def test_a_stale_link_is_repointed(tmp_path):
    skills = tmp_path / ".claude" / "skills"
    skills.mkdir(parents=True)
    (skills / "alteksto").symlink_to(tmp_path / "somewhere-else")

    result = install(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (skills / "alteksto").resolve() == (
        REPO_ROOT / ".claude" / "skills" / "alteksto")


def test_uninstall_takes_back_what_it_registered(tmp_path):
    assert install(tmp_path).returncode == 0

    result = install(tmp_path, "--uninstall")

    assert result.returncode == 0, result.stderr
    for name in LINKS:
        assert not (tmp_path / ".claude" / name).exists()
        assert not (tmp_path / ".claude" / name).is_symlink()
    assert "env" not in settings_of(tmp_path)


def test_uninstall_keeps_other_settings(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text(json.dumps(
        {"model": "opus", "env": {"OTHER": "kept"}}), encoding="utf-8")
    assert install(tmp_path).returncode == 0

    assert install(tmp_path, "--uninstall").returncode == 0

    settings = settings_of(tmp_path)
    assert settings["model"] == "opus"
    assert settings["env"] == {"OTHER": "kept"}


def test_uninstall_leaves_another_checkouts_registration(tmp_path):
    claude = tmp_path / ".claude"
    (claude / "agents").mkdir(parents=True)
    (claude / "skills").mkdir()
    elsewhere = tmp_path / "other-checkout"
    elsewhere.mkdir()
    (claude / "agents" / "prepare-paper.md").symlink_to(elsewhere / "a.md")
    (claude / "settings.json").write_text(json.dumps(
        {"env": {"ALTEKSTO_HOME": str(elsewhere)}}), encoding="utf-8")

    result = install(tmp_path, "--uninstall")

    assert result.returncode == 0, result.stderr
    assert (claude / "agents" / "prepare-paper.md").is_symlink()
    assert settings_of(tmp_path)["env"]["ALTEKSTO_HOME"] == str(elsewhere)
    assert "points elsewhere" in result.stdout


def test_uninstall_with_nothing_installed_is_quiet_success(tmp_path):
    result = install(tmp_path, "--uninstall")

    assert result.returncode == 0, result.stderr
    assert "0 of 3" in result.stdout


def test_a_dangling_registration_fails_loudly(tmp_path):
    """A link into a checkout without these files must not pass silently."""
    fake_root = tmp_path / "checkout"
    shutil.copytree(REPO_ROOT / "tools", fake_root / "tools")
    (fake_root / ".claude" / "agents").mkdir(parents=True)
    # The skill directory is missing, exactly as it is on a revision
    # predating it.
    for name in ("prepare-paper.md", "sweep-paper.md"):
        (fake_root / ".claude" / "agents" / name).write_text("x")

    result = subprocess.run(
        ["bash", str(fake_root / "tools" / "install.sh"), "--links-only"],
        capture_output=True, text=True,
        env={"HOME": str(tmp_path / "home"), "PATH": "/usr/bin:/bin"})

    assert result.returncode == 1
    assert "BROKEN" in result.stdout
