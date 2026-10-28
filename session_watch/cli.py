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
from .browser import Browser, DashboardLoadingError
from .alerts import play_alert
from .core import atomic_write, decide, evidence, digest
from .schedule import next_interval, validate_schedule
from . import invites, pager, alert_store


def emit(root, result):
    event = {"time": datetime.now(timezone.utc).isoformat(), **result}
    line = json.dumps(event)
    print(line, flush=True)
    with (root / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")


def monitor_state(root, phase, **values):
    atomic_write(root / 'monitor-state.json', json.dumps({
        'phase': phase, 'pid': os.getpid(), 'updated_at': time.time(), **values}))


def record_loading_failure(config, root, reason):
    path = root / 'capture-health.json'
    state = json.loads(path.read_text()) if path.exists() else {'consecutive_loading': 0}
    state['consecutive_loading'] += 1
    state['last_reason'] = reason
    if state['consecutive_loading'] >= 3 and not state.get('alert_id'):
        result = {'alert_id': 'loading-' + str(time.time_ns()), 'classification': 'loading_stalled',
                  'confidence': 1, 'reason': 'Three consecutive captures could not finish loading. Monitoring will retry; no PagerDuty notification is sent.',
                  'invite': {'classification': 'not_run', 'confidence': None,
                             'reason': 'The dashboard must finish loading before invitation checks can run.', 'program': '', 'evidence': ''}}
        state['alert_id'] = alert_store.record(root, result)
        play_alert(config, result, root)
    atomic_write(path, json.dumps(state))


def check(config, root, browser):
    baseline = root / "baseline.json"
    before = json.loads(baseline.read_text()) if baseline.exists() else None
    monitor_state(root, "capturing")
    try:
        after = browser.capture()
    except DashboardLoadingError as exc:
        record_loading_failure(config, root, str(exc))
        raise
    recovered_baseline = bool(before and invites.loading(before) and not after.get('auth_signals'))
    if not after.get('auth_signals') and invites.loading(after):
        reason = 'Dashboard is still loading; capture skipped and previous baseline retained.'
        record_loading_failure(config, root, reason)
        raise DashboardLoadingError(reason)
    atomic_write(root / 'capture-health.json', json.dumps({'consecutive_loading': 0}))
    if recovered_baseline:
        before = None
    after["captured_at"] = datetime.now(timezone.utc).isoformat()
    visual = None
    if config.get("screenshots", {}).get("enabled") and not after.get("auth_signals"):
        from .visual import capture_visual
        visual = capture_visual(browser, root, config["screenshots"])
    if visual:
        after["visual"] = visual
    history_path = root / 'recent-snapshots.json'
    history = []
    if history_path.exists() and not recovered_baseline:
        history = json.loads(history_path.read_text())
    snapshot_key = digest(invites.page_text(after, config) + '\n' + (visual or {}).get('image_sha256', ''))
    repeat = bool(before and not after.get('auth_signals') and len(history) >= 2
                  and history[-2]['key'] == snapshot_key and history[-1]['key'] != snapshot_key)
    monitor_state(root, "analyzing")
    result = ({'classification': 'repeat_snapshot', 'confidence': 1, 'advance': True,
               'reason': 'This fully loaded snapshot matches the one from two checks ago (A → B → A). Repeated state; no new alert or PagerDuty notification.'}
              if repeat else decide(before, after, config))
    if recovered_baseline and result['classification'] == 'baseline_created':
        result['reason'] = 'Replaced an incomplete loading baseline with a fully loaded dashboard. Existing rows are not new invites.'
    if visual:
        result["visual"] = visual
    result["captured_at"] = after["captured_at"]
    result["alert_id"] = invites.event_key(before, after, config, visual, root) if before else None
    result["stage1"] = {key: result[key] for key in ["classification", "confidence", "reason"] if key in result}
    if result["classification"] == "auth_expired":
        result["reason"] = result.get("reason") or "; ".join(after.get("auth_signals", [])) or "Sign-in required."
        result["stage1"]["reason"] = result["reason"]
    if config.get("invites", {}).get("enabled"):
        if invites.candidate(before, after, config, result, visual):
            result["checking_invite"] = True
            alert_store.record(root, result)
            monitor_state(root, "classifying_invite")
            result["invite"] = invites.classify_invite(before, after, config, visual)
            # Recall-first: ambiguous/model-failure results alert for review; do not silently lose them.
            result["advance"] = True
            result["checking_invite"] = False
            if result["classification"] == "content_change" and result["invite"]["classification"] in pager.NOTIFY and not alert_store.paused(root):
                event_id = invites.event_key(before, after, config, visual, root)
                result["pager_event_id"] = event_id
                alert_store.record(root, result)
                pager.queue(root, event_id, result["invite"])
        else:
            result["invite"] = {"classification": "not_run", "confidence": None,
                "reason": "No meaningful dashboard change to classify." if result['classification'] != 'auth_expired'
                          else "Sign-in is required before checking for new invitations.", "program": "", "evidence": ""}
            # Invisible script/token changes do not need to keep an obsolete raw baseline.
            if before and result["classification"] == "uncertain":
                result["advance"] = True
    alert_store.record(root, result)
    if before and result["classification"] not in {"unchanged"}:
        event_id = str(time.time_ns())
        atomic_write(root / "changes" / (event_id + ".json"), json.dumps({
            "result": result, "evidence": evidence(before, after, config["llm"].get("max_input_chars", 24000))}, indent=2))
        result["artifact"] = str(root / "changes" / (event_id + ".json"))
    if result["advance"] or result["classification"] in {"baseline_created", "content_change", "unchanged"}:
        browser.save()
    if result["advance"]:
        atomic_write(baseline, json.dumps(after))
    if not after.get('auth_signals'):
        atomic_write(history_path, json.dumps((history + [{'key': snapshot_key, 'captured_at': after['captured_at']}])[-2:]))
    alert = play_alert(config, result, root)
    if alert:
        result["audio_alert"] = alert
    if config.get("invites", {}).get("enabled"):
        analysis_path = root / 'latest-analysis.json'
        if (result.get('invite', {}).get('classification') != 'not_run'
                or result['classification'] == 'auth_expired' or not analysis_path.exists()):
            atomic_write(analysis_path, json.dumps({'time': datetime.now(timezone.utc).isoformat(),
                'stage1': result['stage1'], 'stage2': result['invite'],
                'pager_event_id': result.get('pager_event_id')}))
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
                alert_store.resolve_auth(root)
                emit(root, {"classification": "session_saved", "reason": "Existing baseline preserved"})
            return 0
        if not (root / "storage.json").exists():
            raise RuntimeError("Run session-watch login first")
        if alert_store.paused(root):
            return 2
        with Browser(config, root, headed=args.headed) as browser:
            while True:
                last_error = None
                try:
                    outcome = check(config, root, browser)
                except Exception as exc:
                    last_error = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__ + ": capture/check failed; baseline retained"
                    emit(root, {"classification": "error", "reason": last_error})
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
                monitor_state(root, "waiting", interval_seconds=delay, next_capture_at=time.time() + delay, last_error=last_error)
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
