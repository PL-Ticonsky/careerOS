"""Start/reuse the private local server, then open CareerOS on Linux."""
import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
APP_ID = 'io.careeros.CareerOS'
URL = 'http://127.0.0.1:8765/'
UNIT = 'careeros.service'


def data_home():
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'careeros'


def state_home():
    return Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'careeros'


def internal_uri(uri):
    try:
        parsed = urlparse(uri)
        return parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port == 8765 and not parsed.username and not parsed.password
    except (ValueError, TypeError):
        return False


def server_ready():
    try:
        with urlopen(Request(URL + 'api/health', headers={'User-Agent': 'CareerOS Desktop'}), timeout=1.5) as response:
            data = json.loads(response.read(4096))
            if isinstance(data, dict) and data.get('app') == 'careeros':
                return True
    except HTTPError as error:
        error.close()
        raise RuntimeError('El puerto 8765 está ocupado por otra versión o aplicación. Cierra el servidor anterior de CareerOS y vuelve a abrir la app.') from None
    except (URLError, OSError, ValueError):
        return False
    raise RuntimeError('El puerto 8765 no responde como CareerOS.')


def ensure_server(timeout=30):
    if server_ready():
        return 'existing'
    folder = state_home()
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (folder / 'launch.lock').open('a') as lock:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('CareerOS sigue iniciándose. Vuelve a abrir la app en unos segundos.') from None
                time.sleep(.15)
        if server_ready():
            return 'existing'
        config = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
        unit = config / 'systemd/user' / UNIT
        child = None
        mode = 'service'
        if unit.exists() and shutil.which('systemctl'):
            try:
                result = subprocess.run(['systemctl', '--user', 'start', UNIT], capture_output=True, timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                raise RuntimeError('No se pudo iniciar el servicio de CareerOS. Ejecuta de nuevo instalar_app.py para revisar la instalación.') from None
            if result.returncode:
                raise RuntimeError('El servicio de CareerOS no pudo arrancar. Consulta «systemctl --user status careeros.service».')
        else:
            mode = 'detached'
            log_path = folder / 'server.log'
            fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, 'ab') as log:
                child = subprocess.Popen([sys.executable, str(ROOT / 'app.py')], cwd=ROOT,
                                         stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                         start_new_session=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if server_ready():
                return mode
            if child and child.poll() is not None:
                raise RuntimeError('El servidor no pudo arrancar. Revisa ~/.local/state/careeros/server.log.')
            time.sleep(.2)
        raise RuntimeError('CareerOS tardó demasiado en iniciar. Revisa el estado del servicio o el registro del servidor.')


def main():
    parser = argparse.ArgumentParser(description='Abrir CareerOS como aplicación local.')
    parser.add_argument('--backend-only', action='store_true', help='Iniciar o reutilizar el servidor, sin abrir ventanas.')
    parser.add_argument('--browser', action='store_true', help='Abrir en el navegador habitual.')
    parser.add_argument('--smoke-test', action='store_true', help='Comprobar que la ventana carga y cerrarla automáticamente.')
    args = parser.parse_args()
    if args.backend_only or args.browser:
        try:
            mode = ensure_server()
            print(f'CareerOS listo ({mode}): {URL}')
            if args.browser:
                subprocess.Popen(['xdg-open', URL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return 0
        except RuntimeError as error:
            print(str(error), file=sys.stderr)
            return 1
    try:
        from desktop_window import run
    except (ImportError, ValueError):
        if args.smoke_test:
            print('GTK 4 y WebKitGTK 6 no están disponibles.', file=sys.stderr)
            return 1
        try:
            ensure_server()
            subprocess.Popen(['xdg-open', URL])
            return 0
        except (RuntimeError, OSError) as error:
            print(str(error), file=sys.stderr)
            return 1
    return run(args.smoke_test)


if __name__ == '__main__':
    raise SystemExit(main())
