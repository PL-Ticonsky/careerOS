"""Local-only Google Places credential storage, outside database/backups."""
import json
import os
from pathlib import Path
import re
import tempfile


def key(db):
    environment = os.environ.get('GOOGLE_PLACES_API_KEY', '').strip()
    if environment:
        return environment
    path = Path(db).parent / 'places-private.json'
    if not path.exists():
        return ''
    try:
        value = json.loads(path.read_text()).get('key', '')
    except (OSError, ValueError, AttributeError):
        return ''
    return value if isinstance(value, str) else ''


def status(db):
    configured = bool(key(db))
    return {'configured': configured,
            'source': 'environment' if os.environ.get('GOOGLE_PLACES_API_KEY', '').strip() else 'local' if configured else 'none'}


def save(db, data):
    if os.environ.get('GOOGLE_PLACES_API_KEY', '').strip():
        raise ValueError('El servidor ya usa una clave de entorno; cámbiala allí y reinicia CareerOS.')
    value = data.get('key')
    if not isinstance(value, str) or not re.fullmatch(r'AIza[A-Za-z0-9_-]{20,100}', value.strip()):
        raise ValueError('Introduce una clave de Google Cloud válida, que empieza por AIza.')
    folder = Path(db).parent
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=folder, prefix='.places-', delete=False) as handle:
            temporary = Path(handle.name)
            json.dump({'key': value.strip()}, handle)
        os.chmod(temporary, 0o600)
        os.replace(temporary, folder / 'places-private.json')
    finally:
        if temporary and temporary.exists(): temporary.unlink()
    return status(db)
