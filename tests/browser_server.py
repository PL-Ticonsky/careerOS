"""Isolated, synthetic server for browser checks; never touches personal data or APIs."""
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app

with tempfile.TemporaryDirectory(prefix='careeros-browser-') as folder:
    app.DB = Path(folder) / 'browser.db'
    app.init()
    source = dict(id='synthetic', name='Fuente de prueba', enabled=True, provider='test',
                  url='https://example.com', note='Datos sintéticos para pruebas.', interval_hours=24)
    jobs = [app.normalize('synthetic', f'Python Role {n}', 'Synthetic', 'Colombia',
                          f'https://example.com/role/{n}', 'Python SQL ' * 1000) for n in range(55)]
    jobs.append(app.normalize('synthetic', 'Python Workflow', 'Synthetic', 'Colombia',
                              'https://example.com/workflow', 'Python SQL ' * 1000))
    jobs.append(app.normalize('synthetic', 'Excluded Geography', 'Synthetic', 'Worldwide except Colombia',
                              'https://example.com/excluded', 'Python'))
    app.store(jobs, 'synthetic')
    app.sources = lambda: [source]
    def collect(_):
        time.sleep(1.5)
        return jobs
    app.collect = collect
    app.ThreadingHTTPServer(('127.0.0.1', 8876), app.Handler).serve_forever()
