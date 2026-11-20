"""Start isolated fixtures, run browser checks, and always stop the test server."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
# Refuse an occupied port, rather than accidentally testing a personal server.
with socket.socket() as probe:
    try:
        probe.bind(('127.0.0.1', 8876))
    except OSError:
        raise SystemExit('El puerto de pruebas 8876 está ocupado. Ciérralo o espera a que termine la otra prueba.')
with open(os.devnull, 'w') as log:
    server = subprocess.Popen([sys.executable, 'tests/browser_server.py'], cwd=root, stdout=log, stderr=log)
    try:
        deadline = time.monotonic() + 20
        while True:
            if server.poll() is not None:
                raise RuntimeError('El servidor de pruebas no pudo iniciarse')
            try:
                with socket.create_connection(('127.0.0.1', 8876), timeout=0.2):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('El servidor de pruebas no respondió')
                time.sleep(0.1)
        subprocess.run([sys.executable, 'tests/browser_smoke.py'], cwd=root, check=True)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill(); server.wait()
