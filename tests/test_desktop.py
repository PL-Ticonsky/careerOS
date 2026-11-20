import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import desktop_launcher as launcher
import instalar_app as installer


class Response:
    def __init__(self, data): self.data = data
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, limit): return json.dumps(self.data).encode()


class DesktopTest(unittest.TestCase):
    def test_only_the_local_application_stays_inside_window(self):
        self.assertTrue(launcher.internal_uri('http://127.0.0.1:8765/api/meta'))
        for uri in ['https://example.com','http://localhost:8765','file:///etc/passwd',
                    'http://127.0.0.1:8888','http://user:secret@127.0.0.1:8765',
                    'http://127.0.0.1:bad','javascript:alert(1)']:
            self.assertFalse(launcher.internal_uri(uri),uri)

    def test_health_checks_identity_and_handles_server_absence(self):
        with patch.object(launcher,'urlopen',return_value=Response({'app':'careeros'})):
            self.assertTrue(launcher.server_ready())
        with patch.object(launcher,'urlopen',side_effect=URLError('refused')):
            self.assertFalse(launcher.server_ready())
        for payload in ({'app':'other'},[],{'unrelated':True}):
            with patch.object(launcher,'urlopen',return_value=Response(payload)), self.assertRaises(RuntimeError):
                launcher.server_ready()
        with patch.object(launcher,'urlopen',side_effect=HTTPError(launcher.URL,404,'Not found',{},None)),self.assertRaises(RuntimeError):
            launcher.server_ready()

    def test_running_backend_is_reused_without_starting_processes(self):
        with patch.object(launcher,'server_ready',return_value=True),patch.object(launcher.subprocess,'run') as run,patch.object(launcher.subprocess,'Popen') as popen:
            self.assertEqual(launcher.ensure_server(),'existing')
            run.assert_not_called();popen.assert_not_called()

    def test_start_under_user_service_then_wait_until_ready(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'XDG_CONFIG_HOME':folder,'XDG_STATE_HOME':folder}):
            unit=Path(folder)/'systemd/user/careeros.service';unit.parent.mkdir(parents=True);unit.touch()
            with patch.object(launcher,'server_ready',side_effect=[False,False,False,True]),patch.object(launcher.shutil,'which',return_value='/usr/bin/systemctl'),patch.object(launcher.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run,patch.object(launcher.time,'sleep'):
                self.assertEqual(launcher.ensure_server(),'service')
                self.assertEqual(run.call_args.args[0],['systemctl','--user','start','careeros.service'])

    def test_installer_is_user_scoped_and_preserves_previous_entry(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(installer.shutil,'which',return_value=None):
            data,config=Path(folder)/'share',Path(folder)/'config'
            desktop,service=installer.install(data,config,refresh=False)
            text=desktop.read_text()
            self.assertIn('Name=CareerOS',text);self.assertIn('Terminal=false',text)
            self.assertIn('desktop_launcher.py',text)
            self.assertNotIn('WantedBy=',service.read_text())
            self.assertIn('WorkingDirectory=' + str(installer.ROOT) + '\n',service.read_text())
            self.assertTrue((data/'icons/hicolor/scalable/apps/io.careeros.CareerOS.svg').is_file())
            desktop.write_text('Previous entry')
            installer.install(data,config,refresh=False)
            backups=list(desktop.parent.glob('*.backup-*'))
            self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_text(),'Previous entry')

    def test_exec_arguments_use_desktop_entry_escaping(self):
        self.assertEqual(installer.desktop_argument('/home/me/My App/a.py'),'"/home/me/My App/a.py"')
        self.assertIn('%%',installer.desktop_argument('100% app.py'))
        with self.assertRaises(ValueError):installer.desktop_argument('bad\npath')
