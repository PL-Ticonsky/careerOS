"""A small GTK/WebKit window around the existing local application."""
import os
import re
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('WebKit', '6.0')
from gi.repository import Gtk, WebKit, Gio, GLib
from desktop_launcher import APP_ID, URL, ensure_server, internal_uri, data_home


def run(smoke_test=False):
    GLib.set_application_name('CareerOS')
    GLib.set_prgname(APP_ID)

    class CareerApplication(Gtk.Application):
        def __init__(self):
            super().__init__(application_id=APP_ID + ('.Smoke' if smoke_test else ''), flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
            self.window = None
            self.exit_status = 0
            self.loaded = False

        def do_activate(self):
            if self.window:
                self.window.present()
                return
            self.window = Gtk.ApplicationWindow(application=self, title='CareerOS')
            self.window.set_icon_name(APP_ID)
            self.window.set_default_size(1280, 860)
            self.window.set_titlebar(Gtk.HeaderBar())
            self.window.connect('close-request', self.closed)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
            spinner = Gtk.Spinner(spinning=True)
            box.append(spinner)
            box.append(Gtk.Label(label='Abriendo CareerOS…'))
            self.window.set_child(box)
            self.window.present()
            threading.Thread(target=self.start, daemon=True).start()
            if smoke_test:
                GLib.timeout_add_seconds(35, self.timeout)

        def closed(self, window):
            self.window = None
            return False

        def start(self):
            try:
                ensure_server()
                GLib.idle_add(self.ready)
            except Exception as error:
                GLib.idle_add(self.error, str(error))

        def error(self, message):
            self.exit_status = 1
            print('CareerOS: ' + message, file=sys.stderr, flush=True)
            if smoke_test:
                self.quit()
                return False
            if not self.window:
                return False
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
            label = Gtk.Label(label=message, wrap=True, max_width_chars=70)
            label.set_margin_start(24); label.set_margin_end(24)
            box.append(Gtk.Label(label='No se pudo abrir CareerOS'))
            box.append(label)
            button = Gtk.Button(label='Cerrar')
            button.connect('clicked', lambda _: self.window.close())
            box.append(button)
            self.window.set_child(box)
            return False

        def ready(self):
            if not self.window:
                return False
            store = data_home() / 'webview'
            cache = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'careeros/webview'
            for path in (store, cache):
                path.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.session = WebKit.NetworkSession.new(str(store), str(cache))
            self.session.connect('download-started', self.download_started)
            self.webview = WebKit.WebView(network_session=self.session)
            self.webview.connect('decide-policy', self.policy)
            self.webview.connect('load-changed', self.load_changed)
            self.webview.connect('load-failed', self.load_failed)
            self.window.set_child(self.webview)
            self.webview.load_uri(URL)
            return False

        def policy(self, view, decision, kind):
            if kind not in (WebKit.PolicyDecisionType.NAVIGATION_ACTION, WebKit.PolicyDecisionType.NEW_WINDOW_ACTION):
                return False
            uri = decision.get_navigation_action().get_request().get_uri()
            if internal_uri(uri) or uri.startswith('blob:' + URL) or uri == 'about:blank':
                return False
            if urlparse(uri).scheme in ('http', 'https', 'mailto'):
                try:
                    Gio.AppInfo.launch_default_for_uri(uri, None)
                except GLib.Error:
                    print('CareerOS: no se pudo abrir el enlace externo.', file=sys.stderr)
            decision.ignore()
            return True

        def load_changed(self, view, event):
            if event == WebKit.LoadEvent.FINISHED and internal_uri(view.get_uri() or ''):
                self.loaded = True
                print('CareerOS: ventana cargada.', flush=True)
                if smoke_test:
                    self.quit()

        def load_failed(self, view, event, uri, error):
            if internal_uri(uri) and not self.loaded:
                self.error('No se pudo cargar la interfaz local. Vuelve a abrir CareerOS.')
            return False

        def timeout(self):
            if not self.loaded:
                self.error('La ventana no terminó de cargar durante la comprobación.')
            return False

        def download_started(self, session, download):
            state = {'failed': False}
            def failed(download, error):
                state['failed'] = True
            download.connect('failed', failed)
            def destination(download, suggested):
                folder = Path(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD) or Path.home() / 'Downloads')
                folder.mkdir(parents=True, exist_ok=True)
                filename = re.sub(r'[^\w. -]', '_', Path(suggested or 'careeros-download').name)[:180]
                target = folder / filename
                if target.exists():
                    target = folder / (target.stem + '-' + uuid4().hex[:8] + target.suffix)
                download.set_allow_overwrite(False)
                download.set_destination(str(target))
                return True
            def finished(download):
                if state['failed']:
                    return
                notification = Gio.Notification.new('Descarga de CareerOS completada')
                notification.set_body('El archivo está disponible en tu carpeta de descargas.')
                self.send_notification(None, notification)
            download.connect('decide-destination', destination)
            download.connect('finished', finished)

    application = CareerApplication()
    result = application.run([sys.argv[0]])
    return application.exit_status or result
