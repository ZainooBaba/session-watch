from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import tomllib

from filelock import FileLock, Timeout
from .browser import Browser
from .alerts import play_alert
from .core import atomic_write, decide, evidence
from .schedule import next_interval, validate_schedule


def emit(root, result):
    event = {"time": datetime.now(timezone.utc).isoformat(), **result}
    line = json.dumps(event)
    print(line, flush=True)
    with (root / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")


def monitor_state(root, phase, **values):
    atomic_write(root / 'monitor-state.json', json.dumps({
        'phase': phase, 'pid': os.getpid(), 'updated_at': time.time(), **values}))


def check(config, root, browser):
    baseline = root / "baseline.json"
    before = json.loads(baseline.read_text()) if baseline.exists() else None
    monitor_state(root, "capturing")
    after = browser.capture()
    visual = None
    if config.get("screenshots", {}).get("enabled") and not after.get("auth_signals"):
        from .visual import capture_visual
        visual = capture_visual(browser, root, config["screenshots"])
    monitor_state(root, "analyzing")
    result = decide(before, after, config)
    if visual:
        result["visual"] = visual
    if before and result["classification"] not in {"unchanged"}:
        event_id = str(time.time_ns())
        atomic_write(root / "changes" / (event_id + ".json"), json.dumps({
            "result": result, "evidence": evidence(before, after, config["llm"].get("max_input_chars", 24000))}, indent=2))
        result["artifact"] = str(root / "changes" / (event_id + ".json"))
    if result["classification"] in {"baseline_created", "content_change", "unchanged"}:
        browser.save()
    if result["advance"]:
        atomic_write(baseline, json.dumps(after))
    alert = play_alert(config, result, root)
    if alert:
        result["audio_alert"] = alert
    emit(root, result)
    return result["classification"]


def run(args):
    config_path = Path(args.config).resolve()
    config = tomllib.loads(config_path.read_text())
    if not config.get("url", "").startswith(("https://", "http://")):
        raise ValueError("Set an http(s) URL in config.toml")
    validate_schedule(config)
    if not config.get("llm", {}).get("model"):
        raise ValueError("Set llm.model in config.toml")
    # Sessions and snapshots are private local files, never repository source.
    os.umask(0o077)
    root = (config_path.parent / config.get("state_dir", ".session-watch")).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with FileLock(str(root / "monitor.lock"), timeout=0):
        if args.command == "login":
            with Browser(config, root, headed=True) as browser:
                browser.page.goto(config["url"], wait_until="domcontentloaded")
                input("Complete login in the browser and open the target page. Press Enter here to save: ")
                snapshot = browser.capture()
                if snapshot["auth_signals"]:
                    raise RuntimeError("Login not confirmed: " + "; ".join(snapshot["auth_signals"]))
                browser.save()
                emit(root, {"classification": "session_saved", "reason": "Existing baseline preserved"})
            return 0
        if not (root / "storage.json").exists():
            raise RuntimeError("Run session-watch login first")
        with Browser(config, root, headed=args.headed) as browser:
            while True:
                try:
                    outcome = check(config, root, browser)
                except Exception as exc:
                    emit(root, {"classification": "error", "reason": type(exc).__name__ + ": capture/check failed; baseline retained"})
                    if args.command == "check":
                        return 1
                else:
                    if outcome == "auth_expired":
                        monitor_state(root, "paused")
                        print("Human login required. Run session-watch login, then restart watch.", file=sys.stderr)
                        return 2
                    if args.command == "check":
                        return 3 if outcome == "uncertain" else 0
                delay = next_interval(config)
                monitor_state(root, "waiting", interval_seconds=delay, next_capture_at=time.time() + delay)
                time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description="Monitor authenticated HTML with a local LLM")
    parser.add_argument("command", choices=["login", "check", "watch"])
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    try:
        code = run(args)
    except KeyboardInterrupt:
        code = 130
    except Timeout:
        print("Another login/monitor is using this state directory. Stop it first.", file=sys.stderr)
        code = 1
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
