# Alert requirements

## Purpose

Session Watch watches the authenticated dashboard for newly arriving interview invitations. Every event that needs attention becomes a durable alert object that can be reviewed and dismissed individually. New screenshots, later model results for other events, page refreshes, and app restarts must not silently remove an unread alert.

## Alert levels

| Event | Object | Local sound | PagerDuty | Monitoring |
| --- | --- | --- | --- | --- |
| Authentication is required | Auth Needed | Repeating sign-in sound until dismissed or sign-in action starts | Never | Paused until a verified sign-in succeeds |
| HTML/dashboard change passes the first LLM | Dashboard change | Repeating change sound until dismissed | Not yet | Continues |
| The same change passes both LLM checks as a newly appeared invitation | Upgrade the same object to New interview invite | Repeating change sound until dismissed | Queue one deduplicated notification | Continues |
| First LLM is uncertain but the second finds a possible or confirmed invitation | Change needs review | Repeating change sound until dismissed | Never: both checks have not passed | Continues |
| Second LLM says a confirmed change is not a new invitation | Retain the Dashboard change object and both explanations | Repeating change sound until dismissed | Never | Continues |
| Unchanged page, initial baseline, or unconfirmed raw HTML noise | No new object | None | Never | Continues |

“Passes the first LLM” means its validated result is `content_change`, after the configured confidence and authentication checks. “Passes both” additionally requires the validated second result to be `interview_invite`, including the existing new-evidence and confidence checks. An uncertain first result cannot page, even if the second model is positive. This preserves the preference for cautious local alerts while limiting PagerDuty to new invitations validated by both checks.

## Authentication pause

1. An expired session, visible login form, login redirect, or other supported authentication failure creates one Auth Needed object with the concrete reason.
2. Monitoring stops and an authentication pause is saved to disk. Further change alerts and PagerDuty delivery are suspended during this pause. Existing alert objects are retained.
3. Repeated reports of the same unresolved authentication episode reuse the object; they do not create duplicates.
4. Dismissing the object stops its sound and places it in history. It does not clear the pause, restart monitoring, or claim that authentication has been restored. The status light remains green because sign-in is still needed.
5. Starting the sign-in action silences that authentication alert while keeping it open in New. A successful verified sign-in resolves it, records the resolution time, clears the pause, and resumes monitoring. Unrelated unread change alerts remain open.
6. A restart preserves the authentication pause even when its alert was dismissed. Another expiration after a successful sign-in creates a new episode and a new object.

## Change lifecycle

1. Capture and compare the dashboard against the prior authenticated baseline.
2. When the first LLM confirms a change, persist the alert immediately, before waiting for the second model. The UI indicates that the invitation check is in progress.
3. Store the second model’s result on the same object. Do not create two separate alerts for one detected change.
4. If both checks confirm a new invitation, persist the upgraded object and queue PagerDuty with a stable deduplication key before advancing the baseline.
5. If the user dismissed the initial change while the second check was running, a subsequent confirmed new-invite verdict reopens that object. This is new actionable information. A negative or uncertain second result does not reopen a dismissed confirmed-change object.
6. Persist both model outputs and their update history. Repeated processing of the same event must not duplicate objects or reopen an unchanged dismissed alert.
7. The initial baseline is not a new invitation. Existing scheduled interviews are not new invites merely because the app starts or changes layout.

## Object data and presentation

Every object has a stable ID, category, creation time, most recent update time, revision, and status (`open`, `dismissed`, or `resolved`). It also stores the capture time when available, a human-readable reason, both model classifications and confidence values, returned explanations, supporting invitation evidence, and the associated PagerDuty event ID when applicable. Dismissal and authentication resolution have their own timestamps.

The Alerts tab switches between New (open, undismissed items) and All (including dismissed and resolved history). Each card has a title, Central Time timestamp, explanation, model results when applicable, notification state, and its own Dismiss button. Auth Needed cards also carry the same Sign in / I’m signed in action used in Setup. Alerts are paginated one at a time; the Overview, Change check, and Invite check views have paginated text when needed. Model explanations are displayed as returned outputs; they are not claims to expose hidden model reasoning.

Dismissal targets the exact object and revision shown to the user. If the object gained new information while the user was reading, the app asks them to review the updated item before dismissal. Dismissing one item cannot clear a different item that arrived meanwhile. Rendering model text uses text nodes, not executable HTML.

## Sounds and state

Sign-in uses Basso; changes and invitations use Glass. Sound repeats while an applicable open object remains. Auth Needed takes priority and suspends sounds for other objects until sign-in is restored. Audio failure or disabled audio must not prevent an alert object from being saved.

The indicator remains green while authentication is required, red while a change/review/invite object is open, pulsing yellow while monitoring with no open actionable alerts, and gray while idle. A new screenshot never dismisses objects or clears an authentication pause. Stopping the app stops sound and monitoring but retains unread objects for the next launch. Signing out dismisses local alerts, removes the saved session, and hides private dashboard content while retaining local history.

## PagerDuty and persistence

Only the two-positive-check new-invitation outcome queues PagerDuty. Other changes, auth failures, ambiguity, and model errors stay local. The existing private integration-key setup, retry queue, and deduplication behavior remain in effect. While authentication is paused, queued deliveries wait; successful sign-in permits delivery again.

The UI distinguishes queued delivery from acceptance by PagerDuty. Acceptance confirms receipt by PagerDuty, not that a person received or acknowledged it. Dismissing a local object does not acknowledge or cancel its PagerDuty incident; that action remains in PagerDuty.

Objects are written to private local files independently of sound playback or an open UI. No session cookies, credentials, screenshots, or private dashboard text are added to GitHub. PagerDuty receives the existing generic invitation notification payload.

## Acceptance checks

- A first-stage confirmed change is visible before the second model completes.
- A non-invitation second result retains the first-stage alert and both explanations.
- Two positive checks create one upgraded object and one deduplicated PagerDuty queue entry.
- An uncertain first result cannot page even with a positive second result.
- Auth Needed is durable, deduplicated, and pauses monitoring and further notifications.
- Dismissing Auth Needed silences it without restoring authentication or unpausing monitoring.
- Individual dismissal, update conflicts, history, and unread state survive reloads and restarts.
- Confirmed invitation upgrades reopen an initially dismissed change; identical retries do not.
- Object creation works with audio disabled, and later screenshots cannot clear it.


## Responsive interface

- The app occupies the current viewport using dynamic viewport height, with no scrolling of the main page.
- Home, Dashboard, Alerts, and Setup are separate tabs with keyboard navigation and touch controls.
- Home opens by default with new alerts beside a compact latest-screenshot preview. On narrow screens the preview stacks below the alert. It always filters to undismissed alerts, regardless of the Alerts tab filter.
- Dashboard scales the entire latest screenshot to the available area; opening it full size is an explicit action.
- Alerts offers New and All filters, previous/next item controls, and separate views for the overview and both LLM outputs. Long explanations use text pagination instead of overflowing the viewport.
- Setup contains Session & app and PagerDuty subsections. Sign-in, sign-out, Stop App, and integration settings live there. Auth Needed alerts also offer the sign-in action directly.
- The open-alert count and status light remain visible across tabs. A new screenshot does not change the selected tab or dismiss any alert.
- Portrait phone and short landscape layouts use compact spacing; the screenshot and alert text use the remaining vertical space.
