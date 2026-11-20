"""CareerOS: private, local opportunity workspace. Python 3.11+, no dependencies."""
import argparse
from contextlib import contextmanager, closing
import hashlib
import html
import json
import os
import re
import sqlite3
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import date, datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer as BaseHTTPServer
from pathlib import Path
from urllib.parse import urlparse, urlencode, parse_qs
from urllib.request import Request, urlopen
from career_rules import eligibility, matches
import workspace
import application_analytics
import salary_reference
import opportunity_sources
import discovery
import job_connectors
import event_catalogues
import places_config
import serpapi_connector

class ThreadingHTTPServer(BaseHTTPServer):
    request_queue_size = 64
    daemon_threads = True


ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('CAREEROS_DB', ROOT / 'data/careeros.db'))
LOCK = threading.Lock()
PROGRESS_LOCK = threading.Lock()
SYNC_PROGRESS = {'running': False, 'current': '', 'completed': 0, 'total': 0, 'results': []}
STATES = ['Sin guardar', 'Guardada', 'Postulada', 'Entrevista', 'Oferta', 'Descartada']
SKILLS = ['python', 'sql', 'postgresql', 'fastapi', 'django', 'javascript', 'typescript', 'react', 'data', 'backend', 'api']

def now(): return datetime.now(timezone.utc).isoformat()
def plain(s): return html.unescape(re.sub('<[^>]+>', ' ', html.unescape(str(s or '')))).strip()
def fold(s): return ''.join(c for c in unicodedata.normalize('NFD', str(s).lower()) if unicodedata.category(c) != 'Mn')
def valid_url(s):
    if not isinstance(s,str) or any(ord(c)<32 for c in s): return False
    try:
        p = urlparse(s)
        p.port  # Reject malformed/out-of-range ports as well as unsafe schemes.
        return p.scheme in ('https', 'http') and bool(p.hostname) and not p.username and not p.password
    except ValueError:
        return False

@contextmanager
def connect():
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        with con:
            yield con
    finally:
        con.close()

def init():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        legacy = c.execute("SELECT 1 FROM sqlite_master WHERE name='opportunities'").fetchone()
        migrated = c.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone()
        if legacy and not migrated:
            folder = DB.parent / 'backups'
            folder.mkdir(exist_ok=True)
            target = folder / ('before-migration-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.db')
            with closing(sqlite3.connect(target)) as destination:
                c.backup(destination)
    with connect() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS opportunities(id TEXT PRIMARY KEY, source TEXT NOT NULL, payload TEXT NOT NULL, active INTEGER DEFAULT 1, seen TEXT NOT NULL, status TEXT DEFAULT 'Sin guardar', notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS runs(source TEXT PRIMARY KEY, attempted REAL, success TEXT, count INTEGER DEFAULT 0, error TEXT);
        CREATE TABLE IF NOT EXISTS run_history(id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, started TEXT NOT NULL, finished TEXT NOT NULL, outcome TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 0, rejected INTEGER NOT NULL DEFAULT 0, error TEXT);
        CREATE INDEX IF NOT EXISTS run_history_source ON run_history(source,id DESC);''')
    workspace.migrate(connect)

def normalize(source, title, company, location, url, description='', salary='', published='', mode='', kind='empleo', event_date=''):
    if not valid_url(url) or not isinstance(title,str) or not title.strip(): raise ValueError('Título y URL http(s) válidos son obligatorios')
    company,location,description = company or '',location or '',description or ''
    if not all(isinstance(v,str) for v in (company,location,description,mode,kind,event_date)):
        raise ValueError('La fuente contiene campos de texto inválidos')
    title,company,location = title.strip(),company.strip(),location.strip()
    loc = fold(location)
    mode = mode or ('Remoto' if 'remote' in loc or 'remoto' in loc or 'home based' in loc else 'Por confirmar')
    geographic_signal = eligibility(location)
    text = fold(title + ' ' + plain(description))
    matched = matches(text, SKILLS)
    level = 'Por confirmar'
    for label, pattern in [('Senior', r'\bsenior\b|\bsr\b|\bstaff\b|\bprincipal\b|\blead\b'), ('Junior', r'\bjunior\b|\bjr\b|\bintern\b|\bentry.level\b'), ('Mid', r'\bmid\b|\bintermediate\b')]:
        if re.search(pattern, fold(title)): level = label; break
    return dict(id=hashlib.sha256(url.encode()).hexdigest()[:24], source=source, title=title, company=company, location=location or 'No publicada', url=url, description=plain(description), salary=str(salary or ''), published=str(published or ''), mode=mode, kind=kind, event_date=event_date, eligibility=geographic_signal, skills=matched, level=level, score=min(100, len(matched)*10))

def fetch(url):
    with urlopen(Request(url, headers={'User-Agent':'CareerOS/0.1 personal opportunity reader', 'Accept':'application/json'}), timeout=25) as r:
        return json.load(r)

def sources():
    catalogue = json.loads((ROOT/'sources.json').read_text())
    for source in catalogue:
        if source['provider'] == 'jooble':
            source['enabled'] = bool(job_connectors.jooble_key(DB))
            source['integration_status'] = 'ready' if source['enabled'] else 'needs_key'
            if source['enabled']:
                source['note'] = 'Conexión de Jooble Colombia configurada. Busca desarrollo, Python y datos en Bogotá; hasta 12 consultas por actualización, respetando el intervalo de doce horas.'
    for source in catalogue:
        if source['provider'] == 'serpapi':
            source['enabled'] = bool(serpapi_connector.key(DB))
            source['integration_status'] = 'ready' if source['enabled'] else 'needs_key'
    return catalogue

class Batch(list):
    """Valid records plus diagnostics; a bad record never drops the whole source."""
    def __init__(self):
        super().__init__()
        self.rejected = []


def parse_record(provider, source, j):
    name = source['id']
    if provider == 'jobicy':
        salary = f"{j.get('salaryMin') or '?'}–{j.get('salaryMax') or '?'} {j.get('salaryCurrency') or ''} / {j.get('salaryPeriod') or 'período no publicado'}" if j.get('salaryMin') or j.get('salaryMax') else ''
        return normalize(name,j['jobTitle'],j['companyName'],j.get('jobGeo',''),j['url'],j.get('jobDescription',''),salary,j.get('pubDate',''),'Remoto')
    if provider == 'himalayas':
        if j.get('expiryDate') and j['expiryDate'] <= time.time(): return None
        countries = j.get('locationRestrictions') or []
        zones = j.get('timezoneRestrictions') or []
        salary = f"{j.get('minSalary') or '?'}–{j.get('maxSalary') or '?'} {j.get('currency') or ''} / {j.get('salaryPeriod') or 'período no publicado'}" if j.get('minSalary') or j.get('maxSalary') else ''
        item = normalize(name,j['title'],j['companyName'],', '.join(countries) or 'Worldwide',j['guid'],j.get('description',''),salary,datetime.fromtimestamp(j['pubDate'],timezone.utc).isoformat() if j.get('pubDate') else '', 'Remoto')
        if not valid_url(j['applicationLink']): raise ValueError('Enlace de aplicación inválido')
        item.update(apply_url=j['applicationLink'],timezones=zones,expires=j.get('expiryDate'),employment_type=j.get('employmentType',''))
        item['eligibility'] = 'Compatible por ubicación' if (not countries or 'Colombia' in countries) and (not zones or -5 in zones) else 'Por confirmar'
        return item
    if provider == 'arbeitnow':
        return normalize(name,j['title'],j['company_name'],j.get('location',''),j['url'],j.get('description',''),published=datetime.fromtimestamp(j['created_at'],timezone.utc).isoformat(),mode='Remoto' if j.get('remote') else 'Por confirmar')
    if provider == 'wwr':
        title=j.findtext('title',''); company,sep,role=title.partition(': ')
        return normalize(name,role if sep else title,company if sep else '',j.findtext('region',''),j.findtext('link',''),j.findtext('description',''),published=parsedate_to_datetime(j.findtext('pubDate')).isoformat() if j.findtext('pubDate') else '',mode='Remoto')
    if provider == 'remoteok':
        if not j.get('position') and 'legal' in j: return None
        return normalize(name,j['position'],j.get('company',''),j.get('location',''),j['url'],j.get('description',''),f"{j.get('salary_min')}–{j.get('salary_max')} USD / año" if j.get('salary_min') and j.get('salary_max') else '',j.get('date',''),'Remoto')
    if provider == 'remotive':
        return normalize(name,j['title'],j['company_name'],j.get('candidate_required_location',''),j['url'],j.get('description',''),j.get('salary',''),j.get('publication_date',''),'Remoto')
    if provider == 'greenhouse':
        return normalize(name,j['title'],source['company'],j.get('location',{}).get('name',''),j['absolute_url'],j.get('content',''),published=j.get('first_published',''))
    if provider == 'lever':
        return normalize(name,j['text'],source['company'],j.get('categories',{}).get('location',''),j['hostedUrl'],j.get('descriptionPlain','')+' '+ ' '.join(plain(x.get('content','')) for x in j.get('lists',[])),json.dumps(j['salaryRange']) if j.get('salaryRange') else '',datetime.fromtimestamp(j['createdAt']/1000,timezone.utc).isoformat() if j.get('createdAt') else '', {'remote':'Remoto','hybrid':'Híbrido','on-site':'Presencial'}.get(j.get('workplaceType'),''))
    if provider == 'ashby':
        if not j.get('isListed',True): return None
        return normalize(name,j['title'],source['company'],j.get('location',''),j['jobUrl'],j.get('descriptionPlain',''),(j.get('compensation') or {}).get('compensationTierSummary',''),j.get('publishedAt',''),'Remoto' if j.get('isRemote') else {'Hybrid':'Híbrido','OnSite':'Presencial'}.get(j.get('workplaceType'),''))
    raise ValueError('Proveedor no implementado')


def collect(source):
    provider, board = source['provider'], source.get('board', '')
    if provider == 'serpapi':
        return serpapi_connector.collect(source, serpapi_connector.key(DB), normalize, valid_url, Batch, workspace.local_market, time.sleep)
    if provider == 'mlh':
        return event_catalogues.collect_mlh(source, normalize, valid_url, Batch)
    if provider in ('getonbrd', 'smartrecruiters', 'jooble'):
        return job_connectors.collect(source, fetch, normalize, valid_url, Batch, workspace.local_market, time.sleep, key=job_connectors.jooble_key(DB) if provider == 'jooble' else None)
    if provider == 'opportunity_web':
        return discovery.collect_web(source, normalize, Batch)
    if provider in ('freelancer', 'devpost'):
        return opportunity_sources.collect(source, fetch, normalize, valid_url, plain, Batch, time.sleep)
    if not re.fullmatch(r'[a-zA-Z0-9_-]*', board): raise ValueError('Identificador de empresa inválido')
    batch = Batch()
    seen = set()
    def consume(rows):
        if not isinstance(rows, list): raise ValueError('La fuente no devolvió una lista de ofertas')
        for index, row in enumerate(rows):
            try:
                item = parse_record(provider, source, row)
                if item is not None and (not source.get('market_scope') or workspace.local_market(item) >= 2) and item['id'] not in seen:
                    batch.append(item)
                    seen.add(item['id'])
            except (ValueError, KeyError, TypeError, AttributeError, OverflowError, OSError) as exc:
                # Retain a bounded diagnostic, never raw provider descriptions or credentials.
                batch.rejected.append({'record':index, 'error':type(exc).__name__})
    if provider in ('himalayas','arbeitnow','jobicy'):
        defaults={'himalayas':10,'arbeitnow':3,'jobicy':5}
        pages=source.get('max_pages',defaults[provider])
        if not isinstance(pages,int) or not 1 <= pages <= 100: raise ValueError('max_pages debe estar entre 1 y 100')
        cursor=None; cursors=set()
        for page in range(1,pages+1):
            if provider == 'himalayas':
                data=fetch('https://himalayas.app/jobs/api/search?' + urlencode({'country':'CO','sort':'recent','page':page}))
                rows=data['jobs']; consume(rows)
                if not rows: break
            elif provider == 'arbeitnow':
                data=fetch(f'https://www.arbeitnow.com/api/job-board-api?page={page}')
                consume(data['data'])
                if not data.get('links',{}).get('next'): break
            else:
                params={'count':200}
                if cursor: params['cursor']=cursor
                data=fetch('https://jobicy.com/api/jobs?' + urlencode(params))
                if data.get('success') is False: raise ValueError('La fuente reportó un error')
                consume(data['jobs']); cursor=data.get('nextCursor')
                if not cursor: break
                if cursor in cursors: raise ValueError('La fuente repitió el cursor de paginación')
                cursors.add(cursor)
            if page < pages: time.sleep(1.1)
    elif provider == 'wwr':
        with urlopen(Request('https://weworkremotely.com/remote-jobs.rss',headers={'User-Agent':'CareerOS/0.2'}),timeout=25) as r: root=ET.fromstring(r.read())
        consume(root.findall('./channel/item'))
    else:
        endpoints={
            'remoteok':('https://remoteok.com/api',None),
            'remotive':('https://remotive.com/api/remote-jobs','jobs'),
            'greenhouse':(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true','jobs'),
            'lever':(f'https://api.lever.co/v0/postings/{board}?mode=json',None),
            'ashby':(f'https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true','jobs')}
        if provider not in endpoints: raise ValueError('Proveedor no implementado')
        url,key=endpoints[provider]; data=fetch(url)
        consume(data[key] if key else data)
    if batch.rejected and not batch: raise ValueError(f'Todos los registros fueron rechazados: {len(batch.rejected)}')
    return batch


def store(items, source, deactivate=True):
    workspace.store(connect, items, source, deactivate)

def sync(locked=False):
    if not locked and not LOCK.acquire(blocking=False): return {'busy':True}
    results=[]
    operation = None
    try:
        operation = workspace.acquire_operation(DB)
        if operation is None:
            with PROGRESS_LOCK:
                SYNC_PROGRESS['error'] = 'Otra instancia está actualizando o restaurando esta base de datos.'
            return {'busy':True}
        enabled = [s for s in sources() if s.get('enabled')]
        with PROGRESS_LOCK:
            SYNC_PROGRESS.update(running=True, current='', completed=0, total=len(enabled), results=[], error=None)
        for index, s in enumerate(enabled):
            with PROGRESS_LOCK:
                SYNC_PROGRESS.update(current=s['id'], completed=index, results=list(results))
            with connect() as c: last=c.execute('SELECT * FROM runs WHERE source=?',(s['id'],)).fetchone()
            if last and time.time()-last['attempted'] < (60 if last['error'] else s.get('interval_hours',6)*3600):
                results.append({'source':s['id'],'cached':True}); continue
            started=now()
            try:
                items=collect(s)
                rejected=len(getattr(items,'rejected',[]))
                store(items,s['id'],deactivate=not rejected)
                with connect() as c: c.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?)',(s['id'],time.time(),now(),len(items),None))
                record_run(s['id'],started,'partial' if rejected else 'success',len(items),rejected)
                results.append({'source':s['id'],'count':len(items),'rejected':rejected})
            except Exception as e:
                with connect() as c: c.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?)',(s['id'],time.time(),last['success'] if last else None,last['count'] if last else 0,str(e)))
                record_run(s['id'],started,'error',error=str(e))
                results.append({'source':s['id'],'error':str(e)})
        return {'results':results}
    except Exception as exc:
        with PROGRESS_LOCK:
            SYNC_PROGRESS['error'] = str(exc)
        raise
    finally:
        with PROGRESS_LOCK:
            SYNC_PROGRESS.update(running=False,current='',completed=len(results),results=list(results))
        workspace.release_operation(operation)
        LOCK.release()


def start_sync():
    if not LOCK.acquire(blocking=False):
        return {'busy': True}
    with PROGRESS_LOCK:
        SYNC_PROGRESS.update(running=True, current='', completed=0, total=0, results=[], error=None)
    def work():
        try:
            sync(locked=True)
        except Exception:
            pass  # Reported through /api/sync/progress; keep the server available.
    try:
        threading.Thread(target=work, daemon=True).start()
    except Exception:
        with PROGRESS_LOCK:
            SYNC_PROGRESS.update(running=False,error='No se pudo iniciar la actualización')
        LOCK.release()
        raise
    return {'started': True}

def record_run(source, started, outcome, count=0, rejected=0, error=None):
    with connect() as c:
        c.execute('INSERT INTO run_history(source,started,finished,outcome,count,rejected,error) VALUES (?,?,?,?,?,?,?)',
                  (source,started,now(),outcome,count,rejected,error))
        c.execute('DELETE FROM run_history WHERE id NOT IN (SELECT id FROM run_history ORDER BY id DESC LIMIT 1000)')


def history():
    with connect() as c:
        return [dict(r) for r in c.execute('SELECT * FROM run_history ORDER BY id DESC LIMIT 100')]


def snapshot():
    personal = workspace.profile(connect)
    with connect() as c:
        items=[workspace.decorate(r,personal,True) for r in c.execute('SELECT * FROM opportunities ORDER BY seen DESC')]
        runs={r['source']:dict(r) for r in c.execute('SELECT * FROM runs')}
    
    for item in items:
        if item.get('expires') and item['expires'] <= time.time(): item['active'] = False
    return {'items':items,'sources':[dict(s,run=runs.get(s['id'])) for s in sources()], 'states':STATES,'history':history()}

def text_field(data, key, maximum, required=False):
    value=data.get(key,'')
    if not isinstance(value,str): raise ValueError(f'{key} debe ser texto')
    value=value.strip()
    if required and not value: raise ValueError(f'{key} es obligatorio')
    if len(value)>maximum: raise ValueError(f'{key} supera el máximo de {maximum} caracteres')
    return value


def manual_record(data):
    if data.get('kind') not in ['empleo','freelance','evento']: raise ValueError('Tipo inválido')
    if data.get('mode') not in ['Remoto','Híbrido','Presencial','Por confirmar']: raise ValueError('Modalidad inválida')
    event_date=text_field(data,'event_date',10)
    if event_date:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',event_date): raise ValueError('Fecha inválida; usa AAAA-MM-DD')
        date.fromisoformat(event_date)
    item = normalize('manual',text_field(data,'title',300,True),text_field(data,'company',200),
        text_field(data,'location',200),text_field(data,'url',4096,True),text_field(data,'description',20000),
        text_field(data,'salary',200),mode=data['mode'],kind=data['kind'],event_date=event_date)
    for key, maximum in [('contact_name',200),('contact_email',254),('contact_phone',100),('contact_url',4096),('contact_note',1000),
                         ('requirements',10000),('deliverables',10000),('project_type',100),
                         ('event_type',100),('venue',500),('cost',200),('prizes',300)]:
        item[key] = text_field(data,key,maximum)
    if item['contact_email'] and not re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',item['contact_email']):
        raise ValueError('Correo de contacto inválido')
    if item['contact_url'] and not valid_url(item['contact_url']):
        raise ValueError('Enlace de contacto inválido')
    for key in ('event_end_date','registration_deadline','submission_deadline','project_deadline'):
        item[key] = workspace.valid_date(text_field(data,key,10))
    if event_date and item['event_end_date'] and item['event_end_date'] < event_date:
        raise ValueError('La fecha final no puede ser anterior al inicio')
    if item['kind'] == 'evento':
        item['cost'] = item['cost'] or item['salary']
        item['salary'] = ''
    item.update(description_scope='full', summary=re.sub(r'\s+',' ',item['description']).strip()[:320])
    return item


class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT/'static'),**kwargs)
    def local_host(self):
        try:
            host = urlparse('http://' + self.headers.get('Host',''))
            return host.hostname in ('127.0.0.1','localhost') and (host.port or 80) == self.server.server_port
        except ValueError:
            return False
    def reply(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if not self.local_host(): return self.reply({'error':'Host local no autorizado'},403)
        path = urlparse(self.path)
        params = parse_qs(path.query)
        try:
            if path.path == '/api/health': return self.reply({'app':'careeros','version':1})
            if path.path == '/api/analytics': return self.reply(application_analytics.report(connect,params))
            if path.path == '/api/meta': return self.reply(workspace.metadata(connect,sources(),history()))
            if path.path == '/api/opportunities': return self.reply(workspace.query(connect,params))
            if path.path == '/api/item':
                item = workspace.detail(connect,params.get('id',[''])[0])
                return self.reply(item if item else {'error':'Oportunidad no encontrada'},200 if item else 404)
            if path.path == '/api/sync/progress':
                with PROGRESS_LOCK: progress = dict(SYNC_PROGRESS)
                return self.reply(progress)
            if path.path == '/api/places/status': return self.reply(places_config.status(DB))
            if path.path == '/api/profile': return self.reply(workspace.profile(connect))
            if path.path == '/api/backup': return self.reply(workspace.backup(connect))
            if path.path == '/api/data': return self.reply(snapshot())
            if path.path == '/api/export': return self.reply(snapshot()['items'])
            if path.path == '/api/runs': return self.reply(history())
            if path.path.startswith('/api/'): return self.reply({'error':'Ruta no encontrada'},404)
            return super().do_GET()
        except (ValueError,TypeError,KeyError) as exc:
            return self.reply({'error':str(exc)},400)
        except Exception:
            return self.reply({'error':'No se pudo leer la información local'},500)
    def do_POST(self):
        if not self.local_host(): return self.reply({'error':'Host local no autorizado'},403)
        # JSON-only plus same-origin validation prevents cross-site writes to local data.
        origin=self.headers.get('Origin')
        try:
            if origin and (urlparse(origin).scheme not in ('http','https') or urlparse(origin).netloc != self.headers.get('Host')):
                return self.reply({'error':'Origen no autorizado'},403)
        except ValueError:
            return self.reply({'error':'Origen no autorizado'},403)
        if self.headers.get_content_type() != 'application/json': return self.reply({'error':'Se requiere JSON'},415)
        try:
            size=int(self.headers.get('Content-Length','0'))
            maximum = 100_000_000 if self.path in ('/api/restore/preview','/api/restore') else 200000
            if not 0<size<=maximum: raise ValueError('Tamaño de solicitud inválido')
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict): raise ValueError('Se requiere un objeto JSON')
            if self.path == '/api/sync': return self.reply(sync())
            if self.path == '/api/sync/start': return self.reply(start_sync(),202)
            if self.path == '/api/places/save':
                place_id, label = data.get('place_id'), data.get('label')
                if not isinstance(place_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{5,300}', place_id):
                    raise ValueError('Referencia de Google Maps inválida')
                if not isinstance(label, str) or not 1 <= len(label.strip()) <= 200:
                    raise ValueError('Escribe una referencia personal de hasta 200 caracteres')
                url = 'https://www.google.com/maps/search/?' + urlencode({'api': '1', 'query': 'Google Maps', 'query_place_id': place_id})
                item = normalize('manual', label.strip(), '', 'Bogotá, Colombia', url,
                    description='Referencia personal de un posible cliente. Consulta su ficha en Google Maps y verifica su necesidad antes de contactar.',
                    kind='freelance', mode='Por confirmar')
                item.update(google_place_id=place_id, project_type='Prospecto · sin solicitud de contratación',
                            contact_url=url, contact_note='Referencia guardada desde Google Maps. Los datos del negocio se consultan en la ficha original.')
                with connect() as c:
                    duplicate = c.execute('SELECT 1 FROM opportunities WHERE id=?', (item['id'],)).fetchone() is not None
                if not duplicate: store([item], 'manual', False)
                workspace.update_tracking(connect, {'id': item['id'], 'favorite': True})
                return self.reply({'id': item['id'], 'duplicate': duplicate}, 200 if duplicate else 201)
            if self.path == '/api/places/configure': return self.reply(places_config.save(DB, data))
            if self.path == '/api/places/search': return self.reply(discovery.places_search(data, key=places_config.key(DB)))
            if self.path == '/api/profile': return self.reply(workspace.save_profile(connect,data))
            if self.path == '/api/restore/preview': return self.reply(workspace.restore_preview(connect,data,valid_url))
            if self.path == '/api/restore':
                if not LOCK.acquire(blocking=False): return self.reply({'error':'Espera a que termine la actualización de fuentes'},409)
                operation = None
                try:
                    operation = workspace.acquire_operation(DB)
                    if operation is None: return self.reply({'error':'Otra instancia está actualizando o restaurando esta base de datos'},409)
                    return self.reply(workspace.restore(connect,DB,data,valid_url))
                finally:
                    workspace.release_operation(operation)
                    LOCK.release()
            if self.path == '/api/status':
                if not workspace.update_tracking(connect,data): return self.reply({'error':'Oportunidad no encontrada'},404)
                return self.reply({'ok':True})
            if self.path == '/api/manual':
                j=manual_record(data)
                with connect() as c:
                    if c.execute('SELECT 1 FROM opportunities WHERE id=?',(j['id'],)).fetchone():
                        return self.reply({'duplicate':True,'id':j['id']})
                store([j],'manual',False)
                return self.reply(j,201)
            return self.reply({'error':'Ruta no encontrada'},404)
        except (ValueError,KeyError,TypeError) as e: return self.reply({'error':str(e)},400)
        except Exception: return self.reply({'error':'No se pudo guardar el cambio. Inténtalo nuevamente.'},500)

if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--sync',action='store_true'); parser.add_argument('--port',type=int,default=8765); args=parser.parse_args()
    init()
    if args.sync: print(json.dumps(sync(),ensure_ascii=False,indent=2))
    else:
        salary_reference.start(DB.parent / 'exchange-rates.json')
        print(f'CareerOS disponible en http://127.0.0.1:{args.port}',flush=True)
        ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
