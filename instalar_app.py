"""Register CareerOS in the current user's Linux application launcher."""
import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_ID = 'io.careeros.CareerOS'


def desktop_argument(value):
    # Desktop Entry escaping is deliberately different from shell escaping.
    value = str(value)
    if any(character in value for character in '\n\r\0'):
        raise ValueError('Ruta inválida')
    value = value.replace('%', '%%').replace('\\', '\\\\\\\\')
    for character in ('"', '`', '$'):
        value = value.replace(character, '\\\\' + character)
    return '"' + value + '"'


def unit_argument(value):
    value = str(value)
    if any(character in value for character in '\n\r\0'):
        raise ValueError('Ruta inválida')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'


def write_preserving(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() != content:
        shutil.copy2(path, path.with_name(path.name + '.backup-' + datetime.now().strftime('%Y%m%d%H%M%S%f')))
    path.write_text(content)


def install(data, config, refresh=True):
    python = Path(sys.executable).resolve()
    applications = data / 'applications'
    desktop = applications / (APP_ID + '.desktop')
    icon = data / 'icons/hicolor/scalable/apps' / (APP_ID + '.svg')
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'static/brand-mark.svg', icon)
    launcher_icon = icon
    if shutil.which('rsvg-convert'):
        png = data / 'icons/hicolor/256x256/apps' / (APP_ID + '.png')
        png.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['rsvg-convert', '-w', '256', '-h', '256', '-o', str(png), str(icon)], check=True)
        launcher_icon = png
    write_preserving(desktop, f'''[Desktop Entry]
Version=1.5
Type=Application
Name=CareerOS
GenericName=Gestor de oportunidades profesionales
Comment=Ofertas, freelance, eventos y seguimiento de postulaciones
Exec={desktop_argument(python)} {desktop_argument(ROOT / 'desktop_launcher.py')}
TryExec={python}
Icon={launcher_icon}
Terminal=false
StartupNotify=true
StartupWMClass={APP_ID}
Categories=Office;ProjectManagement;
Keywords=career;empleo;trabajo;freelance;postulaciones;oportunidades;
''')
    desktop.chmod(0o755)
    service = config / 'systemd/user/careeros.service'
    write_preserving(service, f'''[Unit]
Description=CareerOS · servidor privado local

[Service]
Type=exec
WorkingDirectory={str(ROOT).replace(chr(92), chr(92) * 2).replace(chr(37), chr(37) * 2)}
ExecStart={unit_argument(python)} {unit_argument(ROOT / 'app.py')}
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=2
TimeoutStartSec=30
NoNewPrivileges=true
''')
    if shutil.which('desktop-file-validate'):
        subprocess.run(['desktop-file-validate', str(desktop)], check=True)
    if refresh:
        if shutil.which('update-desktop-database'):
            subprocess.run(['update-desktop-database', str(applications)], check=True)
        if shutil.which('systemctl'):
            subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    return desktop, service


def main():
    parser = argparse.ArgumentParser(description='Instalar CareerOS en el buscador de aplicaciones del usuario, sin sudo.')
    parser.add_argument('--data-home', type=Path, default=Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share'))
    parser.add_argument('--config-home', type=Path, default=Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config'))
    parser.add_argument('--no-refresh', action='store_true', help='Preparar archivos sin actualizar el buscador ni systemd (para pruebas).')
    args = parser.parse_args()
    desktop, service = install(args.data_home, args.config_home, not args.no_refresh)
    print('CareerOS instalado. Búscalo por su nombre en el menú de aplicaciones.')
    print('Lanzador:', desktop)
    print('Servicio bajo demanda:', service)
    print('No se ha activado el inicio automático al encender el equipo.')


if __name__ == '__main__':
    main()
