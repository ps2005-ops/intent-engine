"""Scheduler templates and the install/uninstall scripts.

These run the REAL scripts in --dry-run mode. A template that renders to an
invalid plist, or one that leaks a credential, is a production failure that
only shows up on the machine it was installed on.
"""
import os
import re
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPS = os.path.join(REPO, "ops")
TEMPLATES = os.path.join(OPS, "launchd")

pytestmark = pytest.mark.skipif(
    not os.path.isdir(OPS), reason="ops/ not present in this checkout")


def _template(name):
    with open(os.path.join(TEMPLATES, name), encoding="utf-8") as fh:
        return fh.read()


def _render(text, **values):
    for key, value in values.items():
        text = text.replace("{{%s}}" % key, str(value))
    return text


# --- templates --------------------------------------------------------------
def test_both_templates_exist():
    assert os.path.isfile(os.path.join(TEMPLATES, "cycle.plist.template"))
    assert os.path.isfile(os.path.join(TEMPLATES, "health.plist.template"))


def test_a_rendered_cycle_plist_is_valid(tmp_path):
    rendered = _render(_template("cycle.plist.template"),
                       LABEL="com.intentengine.market.day", PYTHON="/usr/bin/python3",
                       REPO="/repo", ROOT="/repo/data", LOGDIR="/logs",
                       CYCLE="day", HOUR=6, MINUTE=30)
    assert "{{" not in rendered
    path = tmp_path / "day.plist"
    path.write_text(rendered)
    out = subprocess.run(["plutil", "-lint", str(path)], capture_output=True)
    assert out.returncode == 0, out.stdout + out.stderr


def test_the_schedule_matches_the_documented_times():
    cycle = _template("cycle.plist.template")
    assert "StartCalendarInterval" in cycle
    assert "{{HOUR}}" in cycle and "{{MINUTE}}" in cycle
    from intent_engine.market.cycle import DAY, NIGHT, SCHEDULE
    assert SCHEDULE[DAY] == (6, 30)
    assert SCHEDULE[NIGHT] == (20, 30)


def test_the_timezone_is_explicit_in_the_plist():
    assert "America/Toronto" in _template("cycle.plist.template")


def test_the_plist_enforces_the_schedule_window():
    """launchd fires on machine-local time; the wrapper checks the operating
    timezone before doing anything."""
    assert "--enforce-window" in _template("cycle.plist.template")


def test_paper_mode_is_pinned_in_both_templates():
    for name in ("cycle.plist.template", "health.plist.template"):
        text = _template(name)
        assert "TRADING_MODE" in text
        assert "PAPER" in text


def test_run_at_load_is_false_for_cycles():
    """A cycle that runs on every login runs at unpredictable times, and this
    system's measurements are indexed by operating day."""
    text = _template("cycle.plist.template")
    assert re.search(r"<key>RunAtLoad</key>\s*<false/>", text)


def test_no_secrets_in_any_template():
    """Scans the PARSED content, so the templates' own prose about credentials
    does not trip the check."""
    for name in os.listdir(TEMPLATES):
        text = _template(name)
        body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        assert not re.search(
            r"(sk-[A-Za-z0-9]{10}|AKIA[0-9A-Z]{8}|"
            r"<string>[A-Za-z0-9_\-]{32,}</string>)", body), name


def test_no_machine_specific_or_scratchpad_paths_are_committed():
    """The templates must be portable. A hard-coded scratchpad path would
    schedule a job against a directory that is deleted when the session ends."""
    for name in os.listdir(TEMPLATES):
        text = _template(name)
        assert "/Users/" not in text, name
        assert "claude-501" not in text, name
        assert "scratchpad" not in text, name


def test_the_health_job_is_not_a_busy_loop():
    text = _template("health.plist.template")
    interval = re.search(r"<key>StartInterval</key>\s*<integer>(\d+)</integer>",
                         text)
    assert interval and int(interval.group(1)) >= 600


def test_the_health_job_does_not_run_a_full_cycle():
    text = _template("health.plist.template")
    assert "<string>status</string>" in text
    assert "<string>day</string>" not in text
    assert "<string>night</string>" not in text


def test_the_cycle_timeout_survives_a_slow_research_sweep():
    text = _template("cycle.plist.template")
    timeout = re.search(r"<key>ExitTimeOut</key>\s*<integer>(\d+)</integer>",
                        text)
    assert timeout and int(timeout.group(1)) >= 900


# --- scripts ----------------------------------------------------------------
def test_install_and_uninstall_scripts_are_executable():
    for name in ("install_autonomous.sh", "uninstall_autonomous.sh"):
        path = os.path.join(OPS, name)
        assert os.path.isfile(path), name
        assert os.access(path, os.X_OK), f"{name} is not executable"


def test_install_dry_run_succeeds_and_installs_nothing():
    before = _installed_labels()
    out = subprocess.run([os.path.join(OPS, "install_autonomous.sh"),
                          "--dry-run"], capture_output=True, text=True,
                         cwd=REPO)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "DRY RUN" in out.stdout
    assert "nothing installed" in out.stdout
    assert "no secrets" in out.stdout
    assert _installed_labels() == before


def test_uninstall_dry_run_removes_nothing():
    before = _installed_labels()
    out = subprocess.run([os.path.join(OPS, "uninstall_autonomous.sh"),
                          "--dry-run"], capture_output=True, text=True,
                         cwd=REPO)
    assert out.returncode == 0, out.stdout + out.stderr
    assert _installed_labels() == before


def test_the_installer_resolves_the_repo_rather_than_hard_coding_it():
    out = subprocess.run([os.path.join(OPS, "install_autonomous.sh"),
                          "--dry-run"], capture_output=True, text=True,
                         cwd=REPO)
    assert os.path.realpath(REPO) in out.stdout


def test_the_installer_unloads_before_loading_so_reruns_cannot_duplicate():
    with open(os.path.join(OPS, "install_autonomous.sh"),
              encoding="utf-8") as fh:
        text = fh.read()
    assert "launchctl bootout" in text
    boot_out = text.index("launchctl bootout")
    boot_in = text.index("launchctl bootstrap")
    assert boot_out < boot_in, "must unload before loading"


def test_the_uninstaller_does_not_delete_research():
    """Turning off the timer is not consent to erase sixteen days of history."""
    with open(os.path.join(OPS, "uninstall_autonomous.sh"),
              encoding="utf-8") as fh:
        text = fh.read()
    assert "rm -rf" not in text
    assert "reports" not in text.split("# WHAT IT DOES NOT TOUCH")[-1][:400] \
        or "untouched" in text


def _installed_labels():
    agents = os.path.expanduser("~/Library/LaunchAgents")
    if not os.path.isdir(agents):
        return []
    return sorted(f for f in os.listdir(agents)
                  if f.startswith("com.intentengine.market"))
