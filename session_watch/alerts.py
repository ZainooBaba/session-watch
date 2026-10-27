"""Distinct, best-effort local audio alerts on macOS."""
import subprocess
import sys
from pathlib import Path


def alert_kind(result):
    if result.get('classification') == 'auth_expired':
        return 'login'
    if (result.get('classification') == 'content_change'
            or result.get('visual', {}).get('classification') == 'visual_change'):
        return 'change'
    return None


def play_alert(config, result):
    settings = config.get('alerts', {})
    kind = alert_kind(result)
    if not settings.get('enabled', False) or kind is None:
        return None
    sound = settings.get('login_sound' if kind == 'login' else 'change_sound',
                         'Basso' if kind == 'login' else 'Glass')
    repeats = 3 if kind == 'login' else 2
    event = {'kind': kind, 'sound': sound, 'repeats': repeats, 'played': False}
    if sys.platform != 'darwin':
        return {**event, 'error': 'Built-in sound playback currently supports macOS only'}
    if not isinstance(sound, str) or not sound.isalnum():
        return {**event, 'error': 'Use a built-in macOS sound name'}
    path = Path('/System/Library/Sounds') / (sound + '.aiff')
    try:
        for _ in range(repeats):
            subprocess.run(['/usr/bin/afplay', '-v', '0.8', str(path)],
                           check=True, timeout=10, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return {**event, 'error': type(exc).__name__ + ': sound playback failed'}
    return {**event, 'played': True}
