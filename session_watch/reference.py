"""Local environment-backed copy fields and an optional availability note."""
import os
import json
import tomllib


def values(config_path, root, include_password=False):
    # Quoted KEY="value" entries work as environment configuration without shell evaluation.
    try:
        local = tomllib.loads((config_path.parent / '.env').read_text())
    except (OSError, ValueError):
        local = {}
    def setting(name):
        value = os.environ.get(name, local.get(name, ''))
        return value if isinstance(value, str) else ''
    try:
        note = json.loads((root / 'reference.json').read_text())
    except (OSError, ValueError):
        note = {}
    shared = bool(note.get('share_password', False))
    return {'email': setting('SESSION_WATCH_EMAIL'),
            'password': setting('SESSION_WATCH_PASSWORD') if include_password or shared else None,
            'availability': str(note.get('availability', '')),
            'password_local_only': not (include_password or shared)}
