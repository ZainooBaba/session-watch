"""Durable, deduplicated PagerDuty Events API v2 delivery."""
from datetime import datetime, timezone
import json
import os
import time

from filelock import FileLock, Timeout
import httpx
from .core import atomic_write

ENDPOINT = 'https://events.pagerduty.com/v2/enqueue'
NOTIFY = {'interview_invite'}


def settings(root, config):
    result = dict(config.get('pager', {}))
    path = root / 'pager-settings.json'
    if path.exists():
        result.update(json.loads(path.read_text()))
    result.setdefault('routing_key', os.environ.get('PAGERDUTY_ROUTING_KEY', ''))
    return result


def save_settings(root, routing_key=None, enabled=True):
    if type(enabled) is not bool:
        raise ValueError('PagerDuty enabled must be true or false.')
    previous = settings(root, {})
    key = routing_key.strip() if isinstance(routing_key, str) and routing_key.strip() else previous.get('routing_key', '')
    if enabled and (not 20 <= len(key) <= 128 or any(c.isspace() for c in key)):
        raise ValueError('Enter your PagerDuty Events API v2 integration routing key.')
    atomic_write(root / 'pager-settings.json', json.dumps({'enabled': enabled, 'routing_key': key}))


def queue(root, event_id, verdict):
    if verdict['classification'] not in NOTIFY:
        return None
    folder = root / 'pager-outbox'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with FileLock(str(root / 'pager.lock'), timeout=5):
        path = folder / (event_id + '.json')
        if not path.exists():
            atomic_write(path, json.dumps({'id': event_id, 'classification': verdict['classification'],
                'confidence': verdict['confidence'], 'created_at': datetime.now(timezone.utc).isoformat(),
                'status': 'pending', 'attempts': 0, 'next_attempt_at': 0}))
    return event_id


def status(root, config, event_id=None):
    configured = settings(root, config)
    records = []
    for path in (root / 'pager-outbox').glob('*.json'):
        try:
            records.append(json.loads(path.read_text()))
        except (OSError, ValueError):
            continue
    delivery = next((r for r in records if r['id'] == event_id), None) if event_id else None
    return {'configured': bool(configured.get('enabled') and configured.get('routing_key')),
            'enabled': bool(configured.get('enabled')), 'has_key': bool(configured.get('routing_key')),
            'pending_count': sum(r['status'] == 'pending' and r['classification'] in NOTIFY for r in records),
            'delivery': delivery}


def dispatch(root, config):
    if (root / 'signed-out').exists():
        return
    current = settings(root, config)
    if not current.get('enabled') or not current.get('routing_key'):
        return
    try:
        with FileLock(str(root / 'pager-delivery.lock'), timeout=0):
            for path in sorted((root / 'pager-outbox').glob('*.json')):
                record = json.loads(path.read_text())
                if record['classification'] not in NOTIFY:
                    record.update(status='local_only', error=None)
                    atomic_write(path, json.dumps(record))
                    continue
                if record['status'] == 'accepted' or record.get('next_attempt_at', 0) > time.time():
                    continue
                record['attempts'] += 1
                payload = {'routing_key': current['routing_key'], 'event_action': 'trigger',
                    'dedup_key': 'session-watch-' + record['id'],
                    'payload': {'summary': 'New interview invitation detected',
                        'source': 'session-watch', 'severity': 'critical',
                        'timestamp': record['created_at'], 'component': 'interview-monitor',
                        'custom_details': {'classification': record['classification'], 'confidence': record['confidence']}}}
                try:
                    with httpx.Client(timeout=15, trust_env=False) as client:
                        response = client.post(ENDPOINT, json=payload)
                        response.raise_for_status()
                        data = response.json()
                        if response.status_code != 202 or not isinstance(data, dict) or data.get('status') != 'success':
                            raise ValueError('Unconfirmed PagerDuty acceptance')
                    record.update(status='accepted', accepted_at=datetime.now(timezone.utc).isoformat(), error=None)
                except (httpx.HTTPError, ValueError, TypeError):
                    record.update(status='pending', error='PagerDuty delivery was not confirmed; retry scheduled.',
                                  next_attempt_at=time.time() + min(600, 30 * 2 ** min(record['attempts'], 4)))
                atomic_write(path, json.dumps(record))
    except Timeout:
        return
