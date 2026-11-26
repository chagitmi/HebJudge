"""Tests for the local UI server (D-45). Offline: the toy agent and a fake judge."""

import json
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import hebjudge.runner as runner
from hebjudge.judge import JudgeResult, JudgeVerdict
from hebjudge.ui.server import App, make_handler

ROOT = Path(__file__).parent.parent


@pytest.fixture
def ui(tmp_path, monkeypatch):
    """A UI server over a copy of the examples, with a fake judge."""
    shutil.copytree(ROOT / "examples", tmp_path / "examples")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "not-used")
    monkeypatch.setenv("HEBJUDGE_HOME", str(tmp_path / "home"))

    def judge(client, scenario, final_text, tool_calls, policy=None):
        verdict = JudgeVerdict(rationale="r", verdict="pass", confidence="high")
        return JudgeResult(verdict, "fake-judge", 1000, 100)

    monkeypatch.setattr(runner, "judge", judge)
    app = App(tmp_path, tmp_path / "data" / "runs" / "traces.sqlite")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(path, body=None, token=app.token, host=None):
        request = urllib.request.Request(base + path, method="POST" if body is not None else "GET")
        if token:
            request.add_header("X-HebJudge-Token", token)
        if host:
            request.add_header("Host", host)
        if body is not None:
            request.add_header("Content-Type", "application/json")
            request.data = json.dumps(body).encode("utf-8")
        try:
            with urllib.request.urlopen(request) as response:
                text = response.read().decode("utf-8")
                return response.status, (json.loads(text) if path.startswith("/api/") else text)
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}") if path.startswith("/api/") else None

    yield app, call
    server.shutdown()


TOY = "examples/targets/toy-python.yaml"


def test_page_carries_the_token_and_api_needs_it(ui):
    app, call = ui
    status, page = call("/", token=None)
    assert status == 200 and app.token in page and 'lang="he"' in page
    assert call("/api/state", token="wrong")[0] == 403
    assert call("/api/state", token=None)[0] == 403
    assert call("/api/state")[0] == 200


def test_other_hosts_are_refused(ui):
    _, call = ui
    assert call("/api/state", host="evil.example.com")[0] == 403


def test_state_lists_targets(ui):
    _, call = ui
    status, state = call("/api/state")
    names = {t["name"] for t in state["targets"]}
    assert "Toy agent (rule-based)" in names
    assert state["scans"] == []


def test_paths_must_stay_inside_the_project(ui):
    _, call = ui
    status, body = call("/api/target?path=../../etc/passwd.yaml")
    assert status == 400 and "תיקיית הפרויקט" in body["error"]


def test_save_new_target_and_refuse_overwriting_examples(ui, tmp_path):
    _, call = ui
    _, loaded = call(f"/api/target?path={TOY}")
    data = loaded["data"]
    data["name"] = "My clinic bot"
    status, saved = call("/api/target/save", {"data": data, "path": None})
    assert status == 200 and saved["path"] == "targets/my-clinic-bot.yaml"
    assert (tmp_path / "targets" / "my-clinic-bot.yaml").exists()
    status, body = call("/api/target/save", {"data": data, "path": TOY})
    assert status == 400 and "קובצי הדוגמה" in body["error"]


def test_save_reports_validation_errors(ui):
    _, call = ui
    status, body = call("/api/target/save", {"data": {"name": "x", "target": {"adapter": "nope"}}})
    assert status == 400 and body["error"]


def test_connection_test(ui):
    _, call = ui
    status, body = call("/api/target/test", {"path": TOY})
    assert status == 200 and "עוזר לדוגמה" in body["reply"]


def test_plan_needs_no_permission_and_sends_nothing(ui):
    app, call = ui
    status, plan = call("/api/scan/plan", {"path": TOY, "level": "quick"})
    assert status == 200
    assert plan["runs"] == 19 and plan["permission"] is False
    assert not app.db_path.exists()


def test_scan_requires_permission(ui):
    _, call = ui
    status, body = call("/api/scan/start", {"path": TOY, "level": "quick"})
    assert status == 400 and "הרשאה" in body["error"]


def test_scan_runs_and_results_and_compare(ui):
    _, call = ui
    batches = []
    for _ in range(2):
        status, started = call(
            "/api/scan/start", {"path": TOY, "level": "quick", "confirm_permission": True}
        )
        assert status == 200
        batch = started["batch"]
        for _ in range(100):
            _, job = call(f"/api/scan/status?batch={batch}")
            if job["state"] != "running":
                break
            time.sleep(0.05)
        assert job["state"] == "done" and job["done"] == 19
        batches.append(batch)

    _, result = call(f"/api/scan/result?batch={batches[0]}")
    goals = {g["goal"]: g for g in result["goals"]}
    assert goals["leak_system_prompt"]["failed"] == 2
    assert result["fixes"] and result["fixes"][0]["he"]
    assert len(result["items"]) == 19

    _, state = call("/api/state")
    assert len(state["scans"]) == 2
    assert state["progress"]["compared"] == []
    _, comparison = call(f"/api/compare?before={batches[0]}&after={batches[1]}")
    assert comparison["common"] == 19 and comparison["fixed"] == []
    _, state = call("/api/state")
    assert state["progress"]["compared"] == ["Toy agent (rule-based)"]


def test_static_files_cannot_escape(ui):
    _, call = ui
    status, _ = call("/../../pyproject.toml", token=None)
    assert status == 404


def test_settings_endpoints_never_return_the_key(ui, monkeypatch):
    _, call = ui
    monkeypatch.delenv("OPENAI_API_KEY")
    status, body = call("/api/settings")
    assert status == 200 and body["set"] is False
    key = "sk-test" + "z" * 40
    status, body = call("/api/settings/key", {"key": key})
    assert status == 200 and body["set"] is True and body["hint"] == "zzzz"
    _, state = call("/api/state")
    assert key not in json.dumps(state)
    status, body = call("/api/settings/key", {"key": "nope"})
    assert status == 400
    _, body = call("/api/settings/key/delete", {})
    assert body["set"] is False


def test_scan_needs_a_key(ui, monkeypatch):
    _, call = ui
    monkeypatch.delenv("OPENAI_API_KEY")
    status, body = call("/api/scan/start", {"path": TOY, "confirm_permission": True})
    assert status == 400 and "מפתח" in body["error"]


def test_init_endpoint_copies_examples(ui, tmp_path):
    _, call = ui
    shutil.rmtree(tmp_path / "examples")
    _, body = call("/api/init", {})
    assert body["written"] > 0 and (tmp_path / "examples" / "toy_agent.py").exists()


# Hardening (D-49) -----------------------------------------------------------------------

TECHNICAL_WORDS = ("forbidden", "bad request", "invalid JSON", "Traceback", "Error", "KeyError")


def _raw(app_call_base, path, data, token):
    """A POST with a body that is not valid JSON, sent as is."""
    request = urllib.request.Request(app_call_base + path, method="POST", data=data)
    request.add_header("X-HebJudge-Token", token)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_every_response_carries_a_content_security_policy(ui):
    app, call = ui
    for path in ("/", "/app.js", "/api/state"):
        request = urllib.request.Request(_base(call) + path)
        request.add_header("X-HebJudge-Token", app.token)
        with urllib.request.urlopen(request) as response:
            policy = response.headers["Content-Security-Policy"]
            assert "script-src 'self'" in policy and "frame-ancestors 'none'" in policy


def _base(call):
    for cell in call.__closure__:
        if isinstance(cell.cell_contents, str) and cell.cell_contents.startswith("http://"):
            return cell.cell_contents
    raise AssertionError("no base address")


def test_refusals_are_in_plain_hebrew(ui):
    app, call = ui
    for status, body in (
        call("/api/state", token="wrong"),
        call("/api/state", host="evil.example.com"),
        call("/api/target"),  # a missing field
        call("/api/target/save", {"nothing": 1}),
        _raw(_base(call), "/api/target/save", b"{not json", app.token),
        _raw(_base(call), "/api/target/save", b"[1, 2]", app.token),
    ):
        assert status in (400, 403), (status, body)
        assert re.search(r"[֐-׿]", body["error"]), body
        assert not any(word in body["error"] for word in TECHNICAL_WORDS), body


def test_an_unexpected_failure_gets_a_plain_message(ui, monkeypatch, capsys):
    app, call = ui

    def broken():
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(app, "scans", broken)
    status, body = call("/api/state")
    assert status == 500 and "השתבש" in body["error"]
    assert "disk on fire" not in body["error"]
    assert "disk on fire" in capsys.readouterr().err  # the details go to the terminal


def test_a_token_typed_into_a_target_file_is_not_saved(ui, tmp_path):
    _, call = ui
    _, loaded = call(f"/api/target?path={TOY}")
    data = loaded["data"]
    data["name"] = "Bot with a token"
    data["target"] = {
        "adapter": "http",
        "url": "https://bot.example.com/chat",
        "headers": {"Authorization": "Bearer abcdefgh12345678"},
        "body": {"message": "{{message}}"},
        "reply_path": "reply",
    }
    status, body = call("/api/target/save", {"data": data, "path": None})
    assert status == 400 and "משתנה סביבה" in body["error"]
    assert not (tmp_path / "targets" / "bot-with-a-token.yaml").exists()
    data["target"]["headers"] = {"Authorization": "Bearer ${BOT_TOKEN}"}
    status, body = call("/api/target/save", {"data": data, "path": None})
    assert status == 200, body


def test_guided_answers_cannot_be_read_from_outside_their_folder(ui, tmp_path):
    _, call = ui
    from hebjudge import wizard

    valid = wizard.Answers(
        mode="instructions", name="בוט", instructions="x", goals=["role_abandonment"]
    )
    text = valid.model_dump_json()
    (tmp_path / "x.wizard.json").write_text(text, encoding="utf-8")  # a real answers file...
    (tmp_path / "examples" / "x.wizard.json").write_text(text, encoding="utf-8")
    for path in ("x.yaml", "examples/x.yaml", "targets/../x.yaml"):  # ...outside targets/
        status, body = call(f"/api/wizard/load?path={path}")
        assert status == 404 and "לא נמצאה" in body["error"], (path, status)
