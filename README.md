# Session Watch

Monitor a website behind a human login. Refresh its rendered HTML on a schedule, detect changes, and ask a locally hosted Ollama model whether the page changed or the login expired.

## How it works

1. `login` opens Chromium. You complete sign-in, SSO, and MFA yourself.
2. Cookies, localStorage, IndexedDB, and sessionStorage are saved locally.
3. `watch` opens the target with that saved session, revisits the configured URL on the configured schedule, waits for rendering, and compares serialized HTML.
4. Identical HTML makes no LLM request. Changed HTML produces redacted before/after excerpts and a diff for Ollama.
5. A confident `content_change` emits an event, saves change evidence, and advances the baseline.
6. `auth_expired` stops the watcher with exit code 2. Log in again and restart. The old content baseline remains, so changes made during expiry can still be detected.
7. `uncertain`, model failures, and browser/server errors retain the baseline. Uncertain results retry on the next cycle. No automated password entry.

Configured login redirects, login elements, missing authenticated elements, and HTTP 401/403 override the model. A 403 can mean permission loss rather than an expired session; either needs human review. Model judgments are probabilistic. Configure `authenticated_selector` for your site to improve reliability.

## Install

Requires Python 3.11+, a desktop for human login, and a running [Ollama](https://ollama.com/download) server. Local inference has no per-request API fee; it uses your own hardware. Model speed and memory needs vary.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
playwright install chromium
# Linux servers may need: playwright install --with-deps chromium
cp config.example.toml config.toml
```

Install Ollama, start its service, and fetch a model (the model name is configurable):

```sh
ollama pull qwen3:8b
# If Ollama is not already running:
ollama serve
```

Edit `config.toml` with your target URL. Set `authenticated_selector` to a stable CSS selector visible only when signed in, such as an account menu. Set `ready_selector` to the actual content region if it renders asynchronously. Adapt `login_url_patterns` and optionally `login_selector` to the site's sign-in flow.

```sh
session-watch login
session-watch check
session-watch watch
```

Log in using the opened browser. Once the target content is visible, press Enter in the terminal. Keep that browser open until the session-saved message appears. The login command revisits the target to confirm session reuse before saving. For diagnosis, use `session-watch check --headed`.

When authentication expires, run `session-watch login`, then `session-watch watch` again. A single lock prevents simultaneous login/watch commands from overwriting each other's saved state. Stop a running watcher before logging in. All commands accept `--config /path/to/config.toml`; state paths are relative to that configuration file.

The first successful check creates the baseline. There is no prior page to classify on that check. Human login plus configured authentication checks establish the initial page.

## Refresh timing

The example configuration uses a truncated normal distribution: mean 90 seconds,
standard deviation 15 seconds, and strict bounds of 60–120 seconds. Samples outside
the bounds are redrawn. The delay begins after each check completes; page loading
and LLM inference add to the time between navigation starts. Remove `[refresh]`
to use the fixed `interval_seconds` setting instead.

```toml
[refresh]
distribution = "truncated_normal"
min_seconds = 60
max_seconds = 120
mean_seconds = 90
stddev_seconds = 15
```

## Results

Console output and `.session-watch/events.jsonl` contain timestamped JSON events. Changed or uncertain pages also create `.session-watch/changes/<id>.json` with the verdict and redacted HTML evidence. No emails or messages are sent. Pipe events to a notification system if needed.

Example:

```json
{"classification":"content_change","confidence":0.95,"reason":"An item was added to the account table","advance":true}
```

`check` exits 0 for a baseline, unchanged page, or confirmed change; 1 for errors; 2 for human login/access review; 3 for uncertainty. `watch` retries transient errors and uncertainty, and exits on auth expiry. Interrupt it with Ctrl+C.

## HTML comparison and privacy

By default, every difference in `page.content()` counts, including scripts, attributes, and dynamic values. This compares the rendered document, not HTTP source bytes, screenshots, shadow DOM, or the contents of separate iframes. `ignore_selectors` and `ignore_attributes` optionally suppress known noisy markup before comparison. A page change that normalizes away will not call the model.

The classifier removes scripts, styles, form values, common token attributes, and URL query strings before sending evidence to the configured Ollama server. Evidence is bounded to avoid oversized prompts; truncation is explicit. Without an authenticated selector, truncated evidence cannot confidently advance the baseline. Scripts-only changes can be uncertain after redaction; the original local baseline is retained.

The default model endpoint is your machine at `127.0.0.1:11434`. Cookies and storage files are never included in model requests. Redaction cannot guarantee all secrets are removed from arbitrary HTML; visible page data can still be sensitive. A remote `llm.base_url` sends that evidence to that server. Website content is treated as untrusted input, and model output is validated; do not treat classification as an access-control boundary.

State files and raw baseline HTML stay in `.session-watch/`, excluded by `.gitignore`. New state directories/files use private permissions. Keep backups private too. Don't commit sessions, custom configs containing secrets, or snapshot files. Keep `state_dir` in an ignored local directory. Change artifacts accumulate; remove old ones according to your retention needs.

Saved state covers common browser auth, but is not a full browser profile. Device-bound credentials, passkeys, anti-bot challenges, and some SSO mechanisms may require site-specific handling or a fresh human login. Only top-level open-page sessionStorage is saved. Monitoring runs on your machine, not in GitHub Actions; CI only tests the project.

## Development

```sh
pytest -q
```

Unit tests exercise baseline preservation, offline/invalid model responses, confidence thresholds, redaction, and truncation. The browser integration test uses a local HTTP fixture, real Chromium, and a mocked model to exercise saved login state, unchanged content, content updates, expired login, and recovery. CI runs tests on Python 3.11–3.13.

Implementation references: [Playwright authentication](https://playwright.dev/python/docs/auth), [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

## Publish to GitHub

From this project directory, with an authenticated GitHub CLI:

```sh
git init -b main
git add .
git commit -m "Build authenticated website change monitor"
gh repo create session-watch --private --source=. --remote=origin --push
```

Use a private repository by default. No website URL or credentials are bundled.

## Screenshot comparison

With `[screenshots] enabled = true`, each successfully authenticated capture also
saves a full-page screenshot at a fixed 1280 × 900 viewport. Local pixel comparison
uses a per-channel tolerance of 20 and flags a visual change when at least 0.1%
of pixels differ or dimensions change. Animations and the text caret are hidden
for capture. This is a visual difference detector; it does not judge the meaning
of a screenshot or send images to the text-only Mistral/Ollama classifier.

The `visual` field in each event reports the result and changed percentage.
`.session-watch/screenshots/` contains `previous.png`, `latest.png`, and
`latest-diff.png` (changed pixels highlighted in pink). Flagged changes also keep
timestamped before/after/diff images. The screenshot baseline advances after every
authenticated capture, independently of the HTML verdict, and is preserved on
auth failure. No screenshot is taken of the login screen. Screenshots may contain
private dashboard information; they stay local and are excluded from GitHub.
