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

LINKS = ("skills/alteksto", "agents/prepare-paper-walk.md",
         "agents/sweep-paper-walk.md")


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
    (agents / "prepare-paper-walk.md").write_text("mine", encoding="utf-8")

    result = install(tmp_path)

    assert result.returncode != 0
    assert "REFUSING" in result.stdout
    assert (agents / "prepare-paper-walk.md").read_text() == "mine"


def test_a_stale_link_is_repointed(tmp_path):
    skills = tmp_path / ".claude" / "skills"
    skills.mkdir(parents=True)
    (skills / "alteksto").symlink_to(tmp_path / "somewhere-else")

    result = install(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (skills / "alteksto").resolve() == (
        REPO_ROOT / ".claude" / "skills" / "alteksto")


def _stale_registration(home):
    """What an install from before the engine rename leaves on a machine.

    Those links named `${ROOT}/.claude/agents/{name}`, which moved into
    the engine, so they resolve to nothing now. They are not in LINK_PATHS
    any more, so nothing takes them back unless the installer knows the
    names it used to use.
    """
    agents = home / ".claude" / "agents"
    agents.mkdir(parents=True)
    for name in ("prepare-paper.md", "sweep-paper.md"):
        (agents / name).symlink_to(REPO_ROOT / ".claude" / "agents" / name)
    other = agents / "someone-elses.md"
    other.symlink_to(home / "other-checkout" / "a.md")
    return agents, other


def test_the_names_used_before_the_engine_rename_are_taken_back(tmp_path):
    agents, other = _stale_registration(tmp_path)

    result = install(tmp_path)

    assert result.returncode == 0, result.stderr
    for name in ("prepare-paper.md", "sweep-paper.md"):
        assert not (agents / name).is_symlink(), name
    # A link into somebody else's checkout is not this one's to remove.
    assert other.is_symlink()


def test_uninstall_takes_back_the_names_used_before_the_rename(tmp_path):
    agents, other = _stale_registration(tmp_path)
    assert install(tmp_path).returncode == 0

    assert install(tmp_path, "--uninstall").returncode == 0

    for name in ("prepare-paper.md", "sweep-paper.md"):
        assert not (agents / name).is_symlink(), name
    assert other.is_symlink()


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
    (claude / "agents" / "prepare-paper-walk.md").symlink_to(
        elsewhere / "a.md")
    (claude / "settings.json").write_text(json.dumps(
        {"env": {"ALTEKSTO_HOME": str(elsewhere)}}), encoding="utf-8")

    result = install(tmp_path, "--uninstall")

    assert result.returncode == 0, result.stderr
    assert (claude / "agents" / "prepare-paper-walk.md").is_symlink()
    assert settings_of(tmp_path)["env"]["ALTEKSTO_HOME"] == str(elsewhere)
    assert "points elsewhere" in result.stdout


def test_uninstall_dry_run_removes_nothing_and_says_so(tmp_path):
    assert install(tmp_path).returncode == 0

    result = install(tmp_path, "--uninstall", "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "would" in result.stdout
    assert "registrations removed" not in result.stdout
    for name in LINKS:
        assert (tmp_path / ".claude" / name).is_symlink()
    assert settings_of(tmp_path)["env"]["ALTEKSTO_HOME"] == str(REPO_ROOT)


def test_a_rerun_does_not_overwrite_the_backup(tmp_path):
    """The backup must keep the file as it stood before any install."""
    claude = tmp_path / ".claude"
    claude.mkdir()
    pristine = json.dumps({"model": "opus"})
    (claude / "settings.json").write_text(pristine, encoding="utf-8")
    assert install(tmp_path).returncode == 0

    assert install(tmp_path).returncode == 0

    backup = json.loads((claude / "settings.json.bak").read_text())
    assert "env" not in backup
    assert backup == {"model": "opus"}


def test_settings_that_are_not_an_object_stop_the_install(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text('["a list"]', encoding="utf-8")

    result = install(tmp_path)

    assert result.returncode != 0
    assert "not a JSON object" in result.stdout + result.stderr
    assert not (claude / "settings.json.bak").exists()


def test_an_env_that_is_not_an_object_stops_the_install(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text(
        json.dumps({"env": "not an object"}), encoding="utf-8")

    result = install(tmp_path)

    assert result.returncode != 0
    assert "not an object" in result.stdout + result.stderr


def test_uninstall_with_nothing_installed_is_quiet_success(tmp_path):
    result = install(tmp_path, "--uninstall")

    assert result.returncode == 0, result.stderr
    assert "0 of 3" in result.stdout


def test_a_dangling_registration_fails_loudly(tmp_path):
    """A link into a checkout without these files must not pass silently."""
    fake_root = tmp_path / "checkout"
    shutil.copytree(REPO_ROOT / "tools", fake_root / "tools")
    agents = fake_root / "engines" / "walk" / "agents"
    agents.mkdir(parents=True)
    # The skill directory is missing, exactly as it is on a revision
    # predating it.
    for name in ("prepare-paper.md", "sweep-paper.md"):
        (agents / name).write_text("x")

    result = subprocess.run(
        ["bash", str(fake_root / "tools" / "install.sh"), "--links-only"],
        capture_output=True, text=True,
        env={"HOME": str(tmp_path / "home"), "PATH": "/usr/bin:/bin"})

    assert result.returncode == 1
    assert "BROKEN" in result.stdout
