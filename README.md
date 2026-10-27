# Session Watch

A local interview-invitation monitor for an authenticated dashboard such as Thalamus. A human signs in once; the app saves the session, refreshes the dashboard, compares HTML and screenshots, and runs two local LLM checks. Authentication failures, LLM-confirmed dashboard changes, and possible invitations create persistent local alert objects. **Only new interview invitations that pass both LLM checks trigger PagerDuty.**

The policy favors recall: an ambiguous meaningful change or a failed invitation classifier alerts for review instead of silently risking a missed invitation. Existing invitations present in the initial baseline are not treated as new.

The detailed behavior and acceptance criteria are in [Alert requirements](ALERT_REQUIREMENTS.md).

## How the two checks work

1. Playwright reloads the dashboard with saved authentication. Identical HTML and screenshots require no LLM call.
2. **Change check:** a local Ollama model distinguishes dashboard changes, expired authentication, and uncertainty. Configured login URLs/elements, HTTP 401/403, and a missing authenticated selector take priority. A model's unsupported login guess cannot override a verified authenticated dashboard.
3. **Invitation check:** a separate structured LLM call compares the old and new dashboard text and focused diff. It returns `interview_invite`, `possible_invite`, or `not_interview_invite`, with confidence, explanation, and a quote when available. Both passes can use the same local model; `[invites.llm]` optionally overrides settings for pass two.
4. Meaningful text or screenshot changes still reach pass two when pass one is uncertain. A confident non-invitation result keeps the confirmed-change alert local; it does not erase or dismiss it. An increasing total/pending invitation counter or an unexplained screenshot-only change is kept as a possible invitation even if the text model tries to rule it out.
5. PagerDuty requires pass one to return `content_change` and pass two to return `interview_invite`. Confirmed new invitations require a verifiable new text quote. An unverifiable claim is downgraded to **possible**, which still alerts locally but never pages. Failed/invalid/offline pass-two responses also become possible local alerts. Routine invisible script/token changes do not page you.
6. The control page displays both decisions, reasons, and quoted evidence. An active alert's review stays pinned while later screenshots arrive. Alert cards retain both model classifications, confidence, returned explanations, and evidence. These are the model’s returned explanations, not hidden internal reasoning.

The text-only model cannot interpret image pixels. Screenshot-only differences can therefore produce possible-invite false positives, including layout/font noise. This is intentional under the recall-first policy. Classification is probabilistic and does not guarantee every invitation will be detected.

## Install and run

Requires Python 3.11+, Chromium, a desktop for human login, and a running [Ollama](https://ollama.com/download) server. Inference runs on your hardware without a per-request model API fee.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
playwright install chromium
# Linux may require: playwright install --with-deps chromium
cp config.example.toml config.toml
ollama pull qwen3:8b
# Start Ollama if it is not already running:
ollama serve
```

Edit `config.toml` with the monitored URL and an installed local model name. The running Thalamus setup can also use `mistral:latest`. Set `authenticated_selector` to a stable element visible only after login; for the Thalamus dashboard this can be `thal-dashboard`. `invites.selector` limits invitation text to the dashboard region; if it does not match, text extraction falls back to the page.

Start the supervisor:

```sh
python -m session_watch.control --config config.toml
```

Open **http://127.0.0.1:8765**. The page has one guided sign-in button:

1. Click **Sign in** to open Chromium and complete sign-in/SSO/MFA yourself.
2. The same button becomes **I'm signed in**. Click it to verify the dashboard, save the session, and automatically resume monitoring.

When monitoring is already healthy, the button says **Sign in again**. When a saved session is simply paused, it offers **Resume monitoring**. Stop an older standalone watcher before starting the supervisor; a lock prevents concurrent use of the same session state.

The first authenticated check creates the comparison baseline. Cookies, localStorage, IndexedDB, and top-level open-page sessionStorage are saved privately. Login failures never replace a good baseline. Device-bound/passkey authentication and some anti-bot/SSO mechanisms may require additional site-specific handling.

## PagerDuty setup

The app uses [PagerDuty Events API v2](https://docs.pagerduty.com/developer/events-api-v2-overview). Create or choose an Events API v2 integration on the PagerDuty service that should notify you, and copy its **Integration Key / routing key**. This is not a general REST API key.

In the local page, expand **PagerDuty setup**, paste that key, and choose **Enable PagerDuty**. The key stays in a private local state file and is never returned by the status API or committed. The app does not send a test incident automatically. Enabling delivery also sends any queued confirmed-invite alerts. **Disable** pauses outbound delivery while local monitoring continues.

- Only confirmed new interview invites create critical trigger events. Possible invites, model uncertainty/failures, sign-in requests, screenshot-only ambiguity, and unrelated changes never trigger PagerDuty. PagerDuty handles recipients, escalation, phone/push/SMS behavior, and acknowledgments according to your service settings.
- Payloads contain a generic invitation/review message, event identifier, classification, and confidence. No dashboard HTML, screenshots, program names, or private interview details are sent.
- Alerts are stored in a durable outbox before the content baseline advances. If PagerDuty is unconfigured or unavailable, they remain queued rather than being discarded.
- The supervisor retries unconfirmed deliveries independently of the watcher, except while authentication is required. Signing out also pauses delivery until signing in again; stopping the app stops the sender.
- A stable event key is reused for retries via PagerDuty's `dedup_key`. Known accepted events are not resent. The page reports **accepted by PagerDuty**, which is not proof a phone notification was delivered. PagerDuty deduplication applies to the corresponding open alert.
- The supervisor checks pending delivery every 15 seconds, with increasing retry backoff after failures. The endpoint is `https://events.pagerduty.com/v2/enqueue`.

For headless configuration, `[pager] enabled = true` can use the `PAGERDUTY_ROUTING_KEY` environment variable. No key is bundled with the project.

## Compact interface

The control page fits the viewport with Dashboard, Alerts, and Setup tabs. The screenshot scales to available space. Alerts can be filtered to **New** or **All**, with one alert per page and paginated explanations. **Setup** holds sign-in, sign-out, Stop App, and PagerDuty settings. Auth Needed alerts also offer sign-in directly: opening sign-in silences the sound, while successful verification resolves the alert and removes it from New.

## Sounds and status

Confirmed dashboard changes create alerts even when the second check rules out a new invitation. The legacy `invite_only` setting no longer suppresses these alerts. Local sounds repeat every eight seconds until the relevant objects are dismissed:

- **Basso three times:** human sign-in/access review required.
- **Glass twice:** confirmed dashboard change, possible invitation, or confirmed new invitation. PagerDuty requires both checks to pass.

On macOS, `alerts.volume = 1.0` uses maximum afplay playback level, subject to your system output volume and mute setting. Sound failures are logged and do not stop monitoring. If the supervisor is unavailable, the watcher falls back to one sound sequence and reports that persistent playback could not be established. Audio currently supports macOS only.

Each alert card has a **Dismiss** button that silences that object and preserves it in history. Other open alerts remain active. A current tone may finish. Acknowledge PagerDuty incidents in PagerDuty separately. The status dot is:

- Pulsing yellow while active.
- Red for an open dashboard-change, review, or invitation alert.
- Green for sign-in or another required action.
- Gray while idle or disconnected.

Unresolved login takes priority. Alert/attention state survives new screenshots, unchanged checks, page reloads, and service restarts until individually dismissed or resolved. Dismissing an auth alert silences it but does not restore the session. A known red/green state is retained during a temporary page connection loss. Reduced-motion preferences disable the pulse.

## Captures and refresh timing

The page shows the latest screenshot and its capture time in **America/Chicago (Central)**. It polls every two seconds, updating the image only when a new capture is saved. Select the image to open it full size. A paused watcher retains the last successful capture and original timestamp.

The thin white bar along the top of the screenshot drains toward the actual next scheduled capture. It switches to Capturing, Comparing, Checking for invitations, or a paused/sign-in state as appropriate. It does not invent a countdown while stopped.

The default schedule uses a truncated normal distribution: mean **90 seconds**, standard deviation **15 seconds**, bounds **60–120 seconds**. Out-of-bounds samples are redrawn. Delay begins after a check finishes; loading and LLM inference add to the time between navigation starts. Remove `[refresh]` to use fixed `interval_seconds`.

HTML comparison uses the rendered `page.content()` document, including scripts and attributes. Optional `ignore_selectors` and `ignore_attributes` suppress known noise. This is not screenshot OCR, shadow-DOM extraction, or separate-iframe source comparison.

Screenshot comparison uses a 1280 × 900 viewport and a full-page PNG, hides animations/carets, and flags differences when at least **0.1%** of pixels exceed a per-channel tolerance of **20**, or image dimensions change. It saves before/after images and a pink-highlighted difference image. The screenshot baseline advances on authenticated captures independently of the invitation review. Login pages are not captured.

Login and background monitoring use the installed Chromium version's normal browser identity. This keeps sites such as Thalamus from returning different interface rollout settings solely because monitoring runs headlessly. Set the target URL to the address you actually use after signing in; different hosts can also serve different layouts.

## Sign out and stop

The footer offers two controls with explanations before confirmation:

- **Sign out:** stops the watcher and login browser, dismisses local alerts, removes saved authentication from this Mac, and hides the dashboard screenshot/review. Existing history stays local. This clears Session Watch's login, not other Thalamus sessions or remote tokens. Next successful sign-in starts a fresh content/screenshot baseline.
- **Stop app:** stops the watcher, login browser, audio, PagerDuty sender, and control service while retaining saved login and queued events. It does not stop a shared Ollama server. Start the supervisor again, or ask the assistant, to resume.

## Local state and privacy

`.session-watch/` is ignored by Git. New state directories/files have private permissions. Contents include:

- `storage.json`, `session.json`: saved authentication; never sent to an LLM or PagerDuty.
- `baseline.json`: raw rendered baseline HTML.
- `events.jsonl`: timestamped monitor decisions and local alert results.
- `changes/`: redacted old/new excerpts, focused diffs, and verdicts.
- `alert-inbox.json`: private alert objects, model explanations, review history, and dismissal timestamps.
- `auth-required.json`: persistent sign-in pause; dismissing an alert does not clear it.
- `screenshots/`: latest/previous/diff PNGs and timestamped visual changes.
- `latest-analysis.json`, `active-alert.json`, `attention.json`: review and latched alert state.
- `pager-settings.json`: private routing key and enable setting.
- `pager-outbox/`: durable queued/accepted minimal notification records.

Model evidence removes scripts, styles, form values, common token attributes, and URL query strings, and bounds input size. Redaction is not guaranteed anonymization; visible dashboard content can still be sensitive. The default endpoint is local `127.0.0.1:11434`; setting a remote LLM URL sends that evidence to the remote server. Page text is treated as untrusted data and structured model outputs are validated.

The control page binds only to loopback, checks Host/Origin, and requires a private token for state changes. Images are served without caching and blocked from cross-origin embedding. Do not expose the server to a network. History accumulates; keep backups private and apply your preferred retention policy.

## CLI and development

The standalone CLI remains available for diagnostics:

```sh
session-watch login
session-watch check --headed
session-watch watch
pytest -q
```

Use the supervisor for persistent audio, the control page, and PagerDuty retries. `check` exits 0 for a baseline/unchanged/confirmed first-pass change, 1 for errors, 2 for login/access review, and 3 for a first-pass uncertain result. In invitation mode, a meaningful uncertain change can still produce a possible-invite alert and advance the baseline after queuing it. `watch` retries transient capture failures and stops on authentication expiry.

Tests cover session persistence and expiry with real Chromium against a local fixture, focused HTML diffs, screenshot comparisons, timing, latched state, sign-in/sign-out/shutdown, both LLM decision gates, recall-first fallbacks, private PagerDuty settings, queued retries, and deduplication. PagerDuty tests mock outbound delivery and never create real incidents. CI runs Python 3.11–3.13.

Implementation references: [Playwright authentication](https://playwright.dev/python/docs/auth), [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [PagerDuty trigger events](https://docs.pagerduty.com/developer/api/reference/events-v2/send-event/create-v2-event).
