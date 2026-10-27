"""Distinct, best-effort local audio alerts on macOS."""
import subprocess
import sys
from pathlib import Path


def alert_kind(result, invite_only=False):
    if result.get('classification') == 'auth_expired':
        return 'login'
    if result.get('invite', {}).get('classification') in {'interview_invite', 'possible_invite'}:
        return 'change'
    if result.get('classification') == 'content_change':
        return 'change'
    if invite_only:
        return None
    if (result.get('classification') == 'content_change'
            or result.get('visual', {}).get('classification') == 'visual_change'):
        return 'change'
    return None


def play_alert(config, result, root=None):
    settings = config.get('alerts', {})
    kind = alert_kind(result, settings.get('invite_only', False))
    if not settings.get('enabled', False) or kind is None:
        return None
    if settings.get('persistent') and root is not None:
        import json
        import httpx
        try:
            control = json.loads((root / 'control.json').read_text())
            with httpx.Client(timeout=5, trust_env=False) as client:
                response = client.post(f"http://127.0.0.1:{int(control['port'])}/event",
                    headers={'X-Session-Watch-Token': control['token']}, json=result)
                response.raise_for_status()
            return {'kind': kind, 'persistent': True, 'queued': True}
        except (OSError, ValueError, KeyError, httpx.HTTPError):
            # A one-shot fallback is audible, but explicitly report the missing loop.
            fallback = play_alert({**config, 'alerts': {**settings, 'persistent': False}}, result)
            return {**(fallback or {}), 'persistent': False,
                    'error': 'Control service unavailable; persistent alert was not queued'}
    category = result.get('alert_category') or ('auth_needed' if kind == 'login' else
        'interview_invite' if result.get('classification') == 'content_change' and result.get('invite', {}).get('classification') == 'interview_invite' else
        'review_needed' if result.get('invite', {}).get('classification') in {'possible_invite', 'interview_invite'} else 'change')
    defaults = {'auth_needed': ('login_sound', 'Basso', 3), 'change': ('change_sound', 'Glass', 2),
                'review_needed': ('review_sound', 'Ping', 2), 'interview_invite': ('invite_sound', 'Hero', 3)}
    key, default, repeats = defaults.get(category, defaults['change'])
    sound = settings.get(key, default)
    volume = settings.get('volume', 1.0)
    event = {'category': category, 'kind': kind, 'sound': sound, 'repeats': repeats, 'volume': volume, 'played': False}
    if sys.platform != 'darwin':
        return {**event, 'error': 'Built-in sound playback currently supports macOS only'}
    if not isinstance(sound, str) or not sound.isalnum():
        return {**event, 'error': 'Use a built-in macOS sound name'}
    if type(volume) not in (int, float) or not 0 <= volume <= 1:
        return {**event, 'error': 'Alert volume must be between 0 and 1'}
    path = Path('/System/Library/Sounds') / (sound + '.aiff')
    try:
        for _ in range(repeats):
            subprocess.run(['/usr/bin/afplay', '-v', str(volume), str(path)],
                           check=True, timeout=10, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return {**event, 'error': type(exc).__name__ + ': sound playback failed'}
    return {**event, 'played': True}
