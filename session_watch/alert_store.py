"""Private, durable alert inbox shared by the watcher and control service."""
from datetime import datetime, timezone
import json
import uuid
from filelock import FileLock
from .core import atomic_write


def now():
    return datetime.now(timezone.utc).isoformat()


def read(root):
    path = root / 'alert-inbox.json'
    return json.loads(path.read_text()) if path.exists() else []


def paused(root):
    return (root / 'auth-required.json').exists()


def record(root, result):
    stage1 = result.get('stage1') or {k: result[k] for k in ('classification', 'confidence', 'reason') if k in result}
    stage2 = result.get('invite') or {'classification': 'not_run', 'reason': 'Invitation check has not run.'}
    auth = result.get('classification') == 'auth_expired'
    passed = stage1.get('classification') == 'content_change'
    confirmed = passed and stage2.get('classification') == 'interview_invite'
    possible = stage2.get('classification') in {'possible_invite', 'interview_invite'}
    if not (auth or passed or possible):
        return None
    with FileLock(str(root / 'alert-inbox.lock'), timeout=5):
        records = read(root)
        if paused(root) and not auth:
            return None
        if auth and paused(root):
            return json.loads((root / 'auth-required.json').read_text())['alert_id']
        event_id = result.get('alert_id') or uuid.uuid4().hex
        item = next((a for a in records if a['id'] == event_id), None)
        if item and result.get('checking_invite') and item['stage2'].get('classification') not in {None, 'not_run'}:
            return event_id
        if item and item['stage1'] == stage1 and item['stage2'] == stage2 and item.get('pager_event_id') == result.get('pager_event_id') and item.get('checking_invite', False) == result.get('checking_invite', False):
            return event_id
        stamp = now()
        category = 'auth_needed' if auth else 'interview_invite' if confirmed else 'change' if passed else 'review_needed'
        if item is None:
            item = {'id': event_id, 'created_at': stamp, 'status': 'open', 'dismissed_at': None,
                    'revision': 0, 'history': []}
            records.append(item)
        elif item['category'] != 'interview_invite' and confirmed:
            # A later positive verdict is new actionable information, even if the initial change was seen.
            item.update(status='open', dismissed_at=None)
        reason = stage1.get('reason') or ('Sign-in is required before monitoring can continue.' if auth else 'The first check confirmed a dashboard change.')
        item.update(category=category, updated_at=stamp, revision=item['revision'] + 1,
                    reason=reason, stage1=stage1, stage2=stage2,
                    pager_event_id=result.get('pager_event_id'), capture_at=result.get('captured_at'),
                    checking_invite=result.get('checking_invite', False))
        item['history'].append({'at': stamp, 'category': category, 'stage1': stage1, 'stage2': stage2})
        atomic_write(root / 'alert-inbox.json', json.dumps(records))
        if auth:
            atomic_write(root / 'auth-required.json', json.dumps({'alert_id': event_id, 'since': stamp}))
        return event_id


def dismiss(root, event_id, revision):
    with FileLock(str(root / 'alert-inbox.lock'), timeout=5):
        records = read(root)
        item = next((a for a in records if a['id'] == event_id), None)
        if item is None:
            raise ValueError('Alert not found.')
        if revision != item['revision']:
            raise ValueError('This alert has new information. Review it before dismissing.')
        if item['status'] == 'open':
            item.update(status='dismissed', dismissed_at=now())
            atomic_write(root / 'alert-inbox.json', json.dumps(records))


def resolve_auth(root):
    with FileLock(str(root / 'alert-inbox.lock'), timeout=5):
        records = read(root)
        for item in records:
            if item['category'] == 'auth_needed' and item['status'] != 'resolved':
                item.update(status='resolved', resolved_at=now())
        atomic_write(root / 'alert-inbox.json', json.dumps(records))
        (root / 'auth-required.json').unlink(missing_ok=True)
