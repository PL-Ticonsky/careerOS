"""CareerOS: private, local opportunity workspace. Python 3.11+, no dependencies."""
import argparse
from contextlib import contextmanager
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
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('CAREEROS_DB', ROOT / 'data/careeros.db'))
LOCK = threading.Lock()
STATES = ['Sin guardar', 'Guardada', 'Postulada', 'Entrevista', 'Oferta', 'Descartada']
SKILLS = ['python', 'sql', 'postgresql', 'fastapi', 'django', 'javascript', 'typescript', 'react', 'data', 'backend', 'api']

def now(): return datetime.now(timezone.utc).isoformat()
def plain(s): return html.unescape(re.sub('<[^>]+>', ' ', html.unescape(str(s or '')))).strip()
def fold(s): return ''.join(c for c in unicodedata.normalize('NFD', str(s).lower()) if unicodedata.category(c) != 'Mn')
def valid_url(s):
    p = urlparse(str(s))
    return p.scheme in ('https', 'http') and bool(p.hostname) and not p.username and not p.password

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
        c.executescript('''CREATE TABLE IF NOT EXISTS opportunities(id TEXT PRIMARY KEY, source TEXT NOT NULL, payload TEXT NOT NULL, active INTEGER DEFAULT 1, seen TEXT NOT NULL, status TEXT DEFAULT 'Sin guardar', notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS runs(source TEXT PRIMARY KEY, attempted REAL, success TEXT, count INTEGER DEFAULT 0, error TEXT);''')

def normalize(source, title, company, location, url, description='', salary='', published='', mode='', kind='empleo', event_date=''):
    if not valid_url(url) or not title: raise ValueError('Título y URL http(s) válidos son obligatorios')
    loc = fold(location)
    mode = mode or ('Remoto' if 'remote' in loc or 'remoto' in loc or 'home based' in loc else 'Por confirmar')
    eligibility = 'Por confirmar'
    if re.search(r'colombia|bogota|latam|latin america|south america|worldwide|anywhere|global', loc):
        eligibility = 'Compatible por ubicación'
    text = fold(title + ' ' + plain(description))
    matched = [s for s in SKILLS if re.search(r'\b' + s + r'\b', text)]
    level = 'Por confirmar'
    for label, pattern in [('Senior', r'\bsenior\b|\bsr\b|\bstaff\b|\bprincipal\b|\blead\b'), ('Junior', r'\bjunior\b|\bjr\b|\bintern\b|\bentry.level\b'), ('Mid', r'\bmid\b|\bintermediate\b')]:
        if re.search(pattern, fold(title)): level = label; break
    return dict(id=hashlib.sha256(url.encode()).hexdigest()[:24], source=source, title=title, company=company, location=location or 'No publicada', url=url, description=plain(description), salary=str(salary or ''), published=str(published or ''), mode=mode, kind=kind, event_date=event_date, eligibility=eligibility, skills=matched, level=level, score=min(100, len(matched)*10))

def fetch(url):
    with urlopen(Request(url, headers={'User-Agent':'CareerOS/0.1 personal opportunity reader', 'Accept':'application/json'}), timeout=25) as r:
        return json.load(r)

def sources(): return json.loads((ROOT/'sources.json').read_text())

def collect(s):
    provider, board = s['provider'], s.get('board', '')
    if not re.fullmatch(r'[a-zA-Z0-9_-]*', board): raise ValueError('Identificador de empresa inválido')
    name = s['id']
    if provider == 'jobicy':
        items = {}; cursor = None
        for page in range(s.get('max_pages', 5)):
            params = {'count':200}
            if cursor: params['cursor'] = cursor
            data = fetch('https://jobicy.com/api/jobs?' + urlencode(params))
            if data.get('success') is False: raise ValueError(data.get('error','Error Jobicy'))
            for j in data['jobs']:
                salary=f"{j.get('salaryMin') or '?'}–{j.get('salaryMax') or '?'} {j.get('salaryCurrency') or ''} / {j.get('salaryPeriod') or 'período no publicado'}" if j.get('salaryMin') or j.get('salaryMax') else ''
                item=normalize(name,j['jobTitle'],j['companyName'],j.get('jobGeo',''),j['url'],j.get('jobDescription',''),salary,j.get('pubDate',''),'Remoto')
                items[item['id']]=item
            cursor=data.get('nextCursor')
            if not cursor: break
            time.sleep(1.1)
        return list(items.values())
    if provider == 'himalayas':
        items = {}
        for page in range(1, s.get('max_pages', 10) + 1):
            data = fetch('https://himalayas.app/jobs/api/search?' + urlencode({'country':'CO','sort':'recent','page':page}))
            jobs = data['jobs']
            if not jobs: break
            for j in jobs:
                if j.get('expiryDate') and j['expiryDate'] <= time.time(): continue
                countries = j.get('locationRestrictions', [])
                zones = j.get('timezoneRestrictions', [])
                salary = f"{j.get('minSalary') or '?'}–{j.get('maxSalary') or '?'} {j.get('currency') or ''} / {j.get('salaryPeriod') or 'período no publicado'}" if j.get('minSalary') or j.get('maxSalary') else ''
                item = normalize(name,j['title'],j['companyName'],', '.join(countries) or 'Worldwide',j['guid'],j.get('description',''),salary,datetime.fromtimestamp(j['pubDate'],timezone.utc).isoformat() if j.get('pubDate') else '', 'Remoto')
                if not valid_url(j['applicationLink']): raise ValueError('Enlace de aplicación inválido')
                item.update(apply_url=j['applicationLink'],timezones=zones,expires=j.get('expiryDate'),employment_type=j.get('employmentType',''))
                item['eligibility'] = 'Compatible por ubicación' if (not countries or 'Colombia' in countries) and (not zones or -5 in zones) else 'Por confirmar'
                items[item['id']]=item
            time.sleep(1.1)
        return list(items.values())
    if provider == 'arbeitnow':
        items=[]
        for page in range(1,s.get('max_pages',3)+1):
            data=fetch(f'https://www.arbeitnow.com/api/job-board-api?page={page}')
            for j in data['data']:
                items.append(normalize(name,j['title'],j['company_name'],j.get('location',''),j['url'],j.get('description',''),published=datetime.fromtimestamp(j['created_at'],timezone.utc).isoformat(),mode='Remoto' if j.get('remote') else 'Por confirmar'))
            if not data.get('links',{}).get('next'): break
        return items
    if provider == 'wwr':
        with urlopen(Request('https://weworkremotely.com/remote-jobs.rss',headers={'User-Agent':'CareerOS/0.1'}),timeout=25) as r: root=ET.fromstring(r.read())
        items=[]
        for j in root.findall('./channel/item'):
            title=j.findtext('title',''); company,sep,role=title.partition(': ')
            items.append(normalize(name,role if sep else title,company if sep else '',j.findtext('region',''),j.findtext('link',''),j.findtext('description',''),published=parsedate_to_datetime(j.findtext('pubDate')).isoformat() if j.findtext('pubDate') else '',mode='Remoto'))
        return items
    if provider == 'remoteok':
        data=fetch('https://remoteok.com/api')
        return [normalize(name,j['position'],j.get('company',''),j.get('location',''),j['url'],j.get('description',''),f"{j.get('salary_min')}–{j.get('salary_max')} USD / año" if j.get('salary_min') and j.get('salary_max') else '',j.get('date',''),'Remoto') for j in data if j.get('position')]

    if provider == 'remotive':
        data = fetch('https://remotive.com/api/remote-jobs')['jobs']
        return [normalize(name,j['title'],j['company_name'],j.get('candidate_required_location',''),j['url'],j.get('description',''),j.get('salary',''),j.get('publication_date',''),'Remoto') for j in data]
    if provider == 'greenhouse':
        data = fetch(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true')['jobs']
        return [normalize(name,j['title'],s['company'],j.get('location',{}).get('name',''),j['absolute_url'],j.get('content','')) for j in data]
    if provider == 'lever':
        data = fetch(f'https://api.lever.co/v0/postings/{board}?mode=json')
        return [normalize(name,j['text'],s['company'],j.get('categories',{}).get('location',''),j['hostedUrl'],j.get('descriptionPlain','')+' '+ ' '.join(plain(x.get('content','')) for x in j.get('lists',[])),json.dumps(j['salaryRange']) if j.get('salaryRange') else '',datetime.fromtimestamp(j['createdAt']/1000,timezone.utc).isoformat() if j.get('createdAt') else '', {'remote':'Remoto','hybrid':'Híbrido','on-site':'Presencial'}.get(j.get('workplaceType'),'')) for j in data]
    if provider == 'ashby':
        data = fetch(f'https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true')['jobs']
        return [normalize(name,j['title'],s['company'],j.get('location',''),j['jobUrl'],j.get('descriptionPlain',''),(j.get('compensation') or {}).get('compensationTierSummary',''),j.get('publishedAt',''),'Remoto' if j.get('isRemote') else {'Hybrid':'Híbrido','OnSite':'Presencial'}.get(j.get('workplaceType'),'')) for j in data if j.get('isListed',True)]
    raise ValueError('Proveedor no implementado')

def store(items, source, deactivate=True):
    with connect() as c:
        if deactivate: c.execute('UPDATE opportunities SET active=0 WHERE source=?',(source,))
        for j in items:
            c.execute('''INSERT INTO opportunities(id,source,payload,active,seen) VALUES (?,?,?,1,?) ON CONFLICT(id) DO UPDATE SET source=excluded.source,payload=excluded.payload,active=1,seen=excluded.seen''',(j['id'],source,json.dumps(j),now()))

def sync():
    if not LOCK.acquire(blocking=False): return {'busy':True}
    results=[]
    try:
        for s in sources():
            if not s.get('enabled'): continue
            with connect() as c: last=c.execute('SELECT * FROM runs WHERE source=?',(s['id'],)).fetchone()
            if last and time.time()-last['attempted'] < (60 if last['error'] else s.get('interval_hours',6)*3600):
                results.append({'source':s['id'],'cached':True}); continue
            try:
                items=collect(s)
                store(items,s['id'])
                with connect() as c: c.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?)',(s['id'],time.time(),now(),len(items),None))
                results.append({'source':s['id'],'count':len(items)})
            except Exception as e:
                with connect() as c: c.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?)',(s['id'],time.time(),last['success'] if last else None,last['count'] if last else 0,str(e)))
                results.append({'source':s['id'],'error':str(e)})
        return {'results':results}
    finally: LOCK.release()

def snapshot():
    with connect() as c:
        items=[dict(json.loads(r['payload']),status=r['status'],notes=r['notes'],active=bool(r['active']),seen=r['seen']) for r in c.execute('SELECT * FROM opportunities ORDER BY seen DESC')]
        runs={r['source']:dict(r) for r in c.execute('SELECT * FROM runs')}
    
    for item in items:
        if item.get('expires') and item['expires'] <= time.time(): item['active'] = False
    return {'items':items,'sources':[dict(s,run=runs.get(s['id'])) for s in sources()], 'states':STATES}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT/'static'),**kwargs)
    def reply(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == '/api/data': return self.reply(snapshot())
        if self.path == '/api/export': return self.reply(snapshot()['items'])
        return super().do_GET()
    def do_POST(self):
        # JSON-only plus same-origin validation prevents cross-site writes to local data.
        origin=self.headers.get('Origin')
        if origin and urlparse(origin).netloc != self.headers.get('Host'): return self.reply({'error':'Origen no autorizado'},403)
        if self.headers.get_content_type() != 'application/json': return self.reply({'error':'Se requiere JSON'},415)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=200000: raise ValueError('Tamaño de solicitud inválido')
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict): raise ValueError('Se requiere un objeto JSON')
            if self.path == '/api/sync': return self.reply(sync())
            if self.path == '/api/status':
                if data['status'] not in STATES: raise ValueError('Estado inválido')
                with connect() as c:
                    result=c.execute('UPDATE opportunities SET status=?,notes=? WHERE id=?',(data['status'],str(data.get('notes',''))[:10000],data['id']))
                    if not result.rowcount: return self.reply({'error':'Oportunidad no encontrada'},404)
                return self.reply({'ok':True})
            if self.path == '/api/manual':
                if data.get('kind') not in ['empleo','freelance','evento']: raise ValueError('Tipo inválido')
                if data.get('mode') not in ['Remoto','Híbrido','Presencial','Por confirmar']: raise ValueError('Modalidad inválida')
                j=normalize('manual',data['title'].strip(),data.get('company',''),data.get('location',''),data['url'].strip(),data.get('description',''),data.get('salary',''),mode=data['mode'],kind=data['kind'],event_date=data.get('event_date',''))
                store([j],'manual',False)
                return self.reply(j,201)
            return self.reply({'error':'Ruta no encontrada'},404)
        except (ValueError,KeyError,TypeError) as e: return self.reply({'error':str(e)},400)

if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--sync',action='store_true'); parser.add_argument('--port',type=int,default=8765); args=parser.parse_args()
    init()
    if args.sync: print(json.dumps(sync(),ensure_ascii=False,indent=2))
    else:
        print(f'CareerOS disponible en http://127.0.0.1:{args.port}',flush=True)
        ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
