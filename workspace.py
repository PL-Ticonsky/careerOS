"""SQLite evolution, paged search and personal workflow. No network access."""
from discovery import eligible_event
from functools import lru_cache
from opportunity_quality import assess
from salary_reference import reference
import hashlib
import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from contextlib import closing

from career_rules import DEFAULT_PROFILE, eligibility, explain, fold, matches_folded, valid_date, validate_profile

STATES = ['Sin guardar', 'Guardada', 'Postulada', 'Entrevista', 'Oferta', 'Descartada']


def now():
    return datetime.now(timezone.utc).isoformat()


def today():
    return datetime.now(timezone(timedelta(hours=-5))).date().isoformat()


def search_text(item):
    return fold(' '.join(str(item.get(k, '')) for k in ('title', 'description')))


def duplicate_key(item):
    company = re.sub(r'\s+', ' ', fold(item.get('company', '')).strip())
    title = re.sub(r'\s+', ' ', fold(item['title']).strip())
    return company + '\n' + title if company else ''


def feed_group(payload, key, item_id):
    """Group presentation only; identical remote descriptions can span cities/titles."""
    item = json.loads(payload)
    if not key:
        return item_id
    location = fold(item.get('location', '')).strip()
    if (item.get('kind') == 'empleo' and item.get('mode') == 'Remoto'
            and local_market(item) >= 2 and len(item.get('description', '').strip()) >= 200):
        description = re.sub(r'\s+', ' ', fold(item.get('description', ''))).strip()
        # Require identical substantive content, the same employer, country,
        # seniority, contract and salary. Technical titles may be worded differently.
        technologies = ['python', 'flask', 'django', 'react', 'angular', 'java', 'javascript',
                        'typescript', 'node', 'php', 'ruby', 'rails', 'golang', 'c++', 'c#',
                        '.net', 'sql', 'kotlin', 'swift', 'rust', 'scala']
        title = re.sub(r'\s+', ' ', fold(item['title'])).strip()
        stack = matches_folded(title, technologies)
        role = stack if len(stack) >= 2 else title
        return json.dumps(['remote-content', fold(item.get('company', '')).strip(), 'colombia',
            role, item.get('level', ''), item.get('employment_type', ''),
            fold(item.get('salary', '')).strip(), hashlib.sha256(description.encode()).hexdigest()])
    return json.dumps([item.get('kind'), key, location,
                       item.get('mode', ''), item.get('employment_type', ''),
                       item.get('event_date', ''), item.get('event_end_date', '')])


def local_market(item):
    location = fold(item.get('location', ''))
    if geo(item) != 'Compatible por ubicación':
        return 0
    if re.search(r'\bbogota\b', location):
        return 3
    if re.search(r'\bcolombia\b', location):
        return 2
    return 1 if item.get('mode') == 'Remoto' else 0


def migrate(connect):
    with connect() as c:
        c.executescript('''
            CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sightings(
                opportunity_id TEXT NOT NULL, source TEXT NOT NULL, payload TEXT NOT NULL,
                active INTEGER NOT NULL, seen TEXT NOT NULL,
                PRIMARY KEY(opportunity_id,source));
            CREATE INDEX IF NOT EXISTS sightings_source ON sightings(source,active,opportunity_id);
            CREATE TABLE IF NOT EXISTS stage_history(
                id INTEGER PRIMARY KEY AUTOINCREMENT, opportunity_id TEXT NOT NULL,
                previous TEXT NOT NULL, status TEXT NOT NULL, changed TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS stage_history_item ON stage_history(opportunity_id,id);
        ''')
        columns = {r['name'] for r in c.execute('PRAGMA table_info(opportunities)')}
        for name in ('applied_date', 'applied_via'):
            if name not in columns:
                c.execute(f"ALTER TABLE opportunities ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
        c.execute('INSERT OR IGNORE INTO schema_migrations VALUES(2,?)', (now(),))
        if c.execute('SELECT 1 FROM schema_migrations WHERE version=1').fetchone():
            return
        columns = {r['name'] for r in c.execute('PRAGMA table_info(opportunities)')}
        for name, definition in [('favorite', 'INTEGER NOT NULL DEFAULT 0'),
                                 ('next_action', "TEXT NOT NULL DEFAULT ''"),
                                 ('due_date', "TEXT NOT NULL DEFAULT ''"),
                                 ('search_text', "TEXT NOT NULL DEFAULT ''"),
                                 ('duplicate_key', "TEXT NOT NULL DEFAULT ''")]:
            if name not in columns:
                c.execute(f'ALTER TABLE opportunities ADD COLUMN {name} {definition}')
        c.execute("UPDATE opportunities SET favorite=1 WHERE status NOT IN ('Sin guardar','Descartada')")
        c.execute('INSERT OR IGNORE INTO sightings SELECT id,source,payload,active,seen FROM opportunities')
        for row in c.execute('SELECT id,payload FROM opportunities').fetchall():
            item = json.loads(row['payload'])
            c.execute('UPDATE opportunities SET search_text=?,duplicate_key=? WHERE id=?',
                      (search_text(item), duplicate_key(item), row['id']))
        c.execute('CREATE INDEX IF NOT EXISTS opportunities_duplicates ON opportunities(duplicate_key)')
        c.execute('CREATE INDEX IF NOT EXISTS opportunities_due ON opportunities(due_date,status)')
        c.execute('INSERT INTO schema_migrations VALUES(1,?)', (now(),))


def profile(connect):
    with connect() as c:
        row = c.execute("SELECT value FROM settings WHERE key='profile'").fetchone()
    return json.loads(row['value']) if row else dict(DEFAULT_PROFILE)


def save_profile(connect, data):
    result = validate_profile(data)
    with connect() as c:
        c.execute("INSERT OR REPLACE INTO settings VALUES('profile',?)", (json.dumps(result),))
    return result


def store(connect, items, source, deactivate=True):
    with connect() as c:
        if deactivate:
            c.execute('UPDATE sightings SET active=0 WHERE source=?', (source,))
        for item in items:
            if source == 'manual' and c.execute('SELECT 1 FROM opportunities WHERE id=?', (item['id'],)).fetchone():
                continue
            stamp = now()
            payload = json.dumps(dict(item, source=source))
            c.execute('''INSERT INTO sightings VALUES(?,?,?,1,?)
                ON CONFLICT(opportunity_id,source) DO UPDATE SET
                payload=excluded.payload,active=1,seen=excluded.seen''',
                      (item['id'], source, payload, stamp))
            c.execute('''INSERT INTO opportunities(id,source,payload,active,seen,search_text,duplicate_key)
                VALUES(?,?,?,1,?,?,?) ON CONFLICT(id) DO UPDATE SET
                payload=CASE WHEN opportunities.source=excluded.source THEN excluded.payload ELSE opportunities.payload END,
                search_text=CASE WHEN opportunities.source=excluded.source THEN excluded.search_text ELSE opportunities.search_text END,
                duplicate_key=CASE WHEN opportunities.source=excluded.source THEN excluded.duplicate_key ELSE opportunities.duplicate_key END,
                seen=excluded.seen''',
                      (item['id'], source, payload, stamp, search_text(item), duplicate_key(item)))
        # Each source owns only its sightings. An absent URL in one feed cannot
        # deactivate a matching URL still present in another feed.
        c.execute('''UPDATE opportunities SET active=EXISTS(
            SELECT 1 FROM sightings s WHERE s.opportunity_id=opportunities.id AND s.active=1)''')
        # If the original source drops a URL, use a still-active observation.
        # Retain every source observation, and never touch personal fields.
        stale = c.execute('''SELECT o.id FROM opportunities o WHERE o.active=1 AND NOT EXISTS(
            SELECT 1 FROM sightings s WHERE s.opportunity_id=o.id AND s.source=o.source AND s.active=1)''').fetchall()
        for row in stale:
            sighting = c.execute('SELECT * FROM sightings WHERE opportunity_id=? AND active=1 ORDER BY seen DESC,source LIMIT 1', (row['id'],)).fetchone()
            item = json.loads(sighting['payload'])
            c.execute('UPDATE opportunities SET source=?,payload=?,search_text=?,duplicate_key=? WHERE id=?',
                      (sighting['source'], sighting['payload'], search_text(item), duplicate_key(item), row['id']))


def geo(item):
    result = eligibility(item.get('location', ''))
    if item.get('timezones') and -5 not in item['timezones']:
        return 'Por confirmar'
    return result


def availability(item, active):
    if item.get('closed') is True:
        return 'Cierre confirmado'
    if item.get('expires') and item['expires'] <= time.time():
        return 'Vencida'
    if item.get('kind') == 'evento' and item.get('event_end_date') and item['event_end_date'] < today():
        return 'Vencida'
    if item.get('refresh_before') and item['refresh_before'] <= time.time():
        return 'Actualización pendiente'
    return 'En el último lote' if active else 'Fuera del lote'


def decorate(row, personal, detail=False):
    item = json.loads(row['payload'])
    skills, score, reasons = explain(item, personal)
    item.update({key: row[key] for key in ('status', 'notes', 'seen', 'next_action', 'due_date', 'applied_date', 'applied_via')})
    item.update(favorite=bool(row['favorite']), eligibility=geo(item), skills=skills,
                score=score, match_reasons=reasons, availability=availability(item, row['active']))
    item['active'] = item['availability'] == 'En el último lote'
    item['quality'] = assess(item, personal)
    item['salary_reference'] = reference(item)
    if not detail:
        if item.get('kind') in ('freelance','evento'):
            item['summary'] = item.get('summary') or re.sub(r'\s+', ' ', item.get('description', '')).strip()[:320]
        for key in ('description', 'notes'):
            item.pop(key, None)
    return item


def metadata(connect, sources, history):
    personal = profile(connect)
    with connect() as c:
        c.create_function('available', 2, lambda p, a: int(availability(json.loads(p), a) == 'En el último lote' and (json.loads(p).get('kind') != 'evento' or (eligible_event(json.loads(p)) and not json.loads(p).get('discovery_only')))))
        c.create_function('compatible', 1, lambda p: int(geo(json.loads(p)) == 'Compatible por ubicación'))
        totals = dict(c.execute('''SELECT COUNT(*) AS total,
            COALESCE(SUM(available(payload,active)),0) AS active,
            COALESCE(SUM(available(payload,active)*compatible(payload)),0) AS compatible,
            COALESCE(SUM(favorite=1 OR status NOT IN ('Sin guardar','Descartada')),0) AS tracking,
            COALESCE(SUM(due_date<>'' AND due_date<=? AND status NOT IN ('Oferta','Descartada')),0) AS due
            FROM opportunities''', (today(),)).fetchone())
        stages = {r['status']: r['n'] for r in c.execute('SELECT status,COUNT(*) n FROM opportunities GROUP BY status')}
        by_kind = {r['kind']: dict(r) for r in c.execute('''SELECT json_extract(payload,'$.kind') AS kind,
            COUNT(*) AS total, COALESCE(SUM(available(payload,active)),0) AS active,
            COALESCE(SUM(available(payload,active)*compatible(payload)),0) AS compatible,
            COALESCE(SUM(favorite=1 OR status NOT IN ('Sin guardar','Descartada')),0) AS tracking,
            COALESCE(SUM(due_date<>'' AND due_date<=? AND status NOT IN ('Oferta','Descartada')),0) AS due
            FROM opportunities GROUP BY json_extract(payload,'$.kind')''', (today(),))}
        runs = {r['source']: dict(r) for r in c.execute('SELECT * FROM runs')}
        duplicates = c.execute("SELECT COUNT(*) FROM (SELECT duplicate_key FROM opportunities WHERE duplicate_key<>'' GROUP BY duplicate_key HAVING COUNT(*)>1)").fetchone()[0]
    return {'sources': [dict(s, run=runs.get(s['id'])) for s in sources],
            'states': STATES, 'history': history, 'profile': personal,
            'stats': dict(totals, stages=stages, duplicate_groups=duplicates, by_kind=by_kind)}


def query(connect, params):
    personal = profile(connect)
    def value(key, default=''):
        return params.get(key, [default])[0]
    try:
        limit, offset = int(value('limit', '24')), int(value('offset', '0'))
    except ValueError:
        raise ValueError('Paginación inválida') from None
    if not 1 <= limit <= 100 or not 0 <= offset <= 1000000:
        raise ValueError('Paginación fuera de rango')
    view = value('view', 'empleo')
    if view not in ('empleo', 'freelance', 'evento', 'tracking'):
        raise ValueError('Vista inválida')
    where, args = [], []
    grouped = view != 'tracking' and value('ungrouped') != '1'
    market = value('market')
    if market not in ('', 'colombia', 'bogota', 'compatible'):
        raise ValueError('Mercado inválido')
    if market == 'colombia':
        where.append('local_market(o.payload)>=2')
    elif market == 'bogota':
        where.append('local_market(o.payload)=3')
    elif market == 'compatible':
        where.append('local_market(o.payload)>=1')
    if view == 'tracking':
        where.append("(o.favorite=1 OR o.status<>'Sin guardar')")
    else:
        where.append("json_extract(o.payload,'$.kind')=?")
        args.append(view)
        if value('show_saved') != '1' and value('favorite') != '1':
            # Hide the entire display group when any variant is already handled.
            where.append('unhandled(o.payload,o.duplicate_key,o.id)=1')
        if value('inactive') != '1':
            where.append('available(o.payload,o.active)=1')
    if view == 'evento':
        if value('discovery') == '1':
            where.append("json_extract(o.payload,'$.discovery_only')=1")
        else:
            where.append("event_allowed(o.payload)=1 AND COALESCE(json_extract(o.payload,'$.discovery_only'),0)=0")
        if value('event_type'):
            where.append("json_extract(o.payload,'$.event_type')=?"); args.append(value('event_type'))
        if value('free') == '1':
            where.append("fold(COALESCE(json_extract(o.payload,'$.cost'),'')) IN ('gratis','gratuito','0')")
    for key in ('query', 'location'):
        if value(key):
            if key == 'query':
                where.append("(instr(o.search_text,?)>0 OR instr(fold(json_extract(o.payload,'$.company')),?)>0)")
                args.extend([fold(value(key))] * 2)
            else:
                where.append("instr(fold(json_extract(o.payload,'$.location')),?)>0")
                args.append(fold(value(key)))
    for key in ('mode', 'level'):
        if value(key):
            where.append(f"json_extract(o.payload,'$.{key}')=?")
            args.append(value(key))
    if value('source'):
        where.append('EXISTS(SELECT 1 FROM sightings s WHERE s.opportunity_id=o.id AND s.source=?)')
        args.append(value('source'))
    if value('eligibility'):
        where.append('geo(o.payload)=?')
        args.append(value('eligibility'))
    if value('salary') == '1':
        where.append("COALESCE(json_extract(o.payload,'$.cost'),'')<>''" if view == 'evento' else "COALESCE(json_extract(o.payload,'$.salary'),'')<>''")
    if value('favorite') == '1':
        where.append('o.favorite=1')
    if value('due') == '1':
        where.append("o.due_date<>'' AND o.due_date<=? AND o.status NOT IN ('Oferta','Descartada')")
        args.append(today())
    if value('status'):
        if value('status') not in STATES:
            raise ValueError('Estado inválido')
        where.append('o.status=?')
        args.append(value('status'))
    priority = value('priority')
    if priority not in ('', 'top', 'matched', 'low_competition'):
        raise ValueError('Filtro de relevancia inválido')
    if priority:
        where.append('quality_' + priority + '(o.payload,o.active)=1')
    orders = {'relevance': "priority(o.payload,o.active) DESC,local_market(o.payload) DESC,score(o.search_text,json_extract(o.payload,'$.mode'),json_extract(o.payload,'$.level'),json_extract(o.payload,'$.location')) DESC,o.id", 'local': "local_market(o.payload) DESC,score(o.search_text,json_extract(o.payload,'$.mode'),json_extract(o.payload,'$.level'),json_extract(o.payload,'$.location')) DESC,o.id",
              'match': "score(o.search_text,json_extract(o.payload,'$.mode'),json_extract(o.payload,'$.level'),json_extract(o.payload,'$.location')) DESC,o.id",
              'company': "fold(json_extract(o.payload,'$.company')),o.id",
              'recent': "COALESCE(julianday(json_extract(o.payload,'$.published')),0) DESC,o.id",
              'event': "COALESCE(NULLIF(json_extract(o.payload,'$.submission_deadline'),''),NULLIF(json_extract(o.payload,'$.registration_deadline'),''),NULLIF(json_extract(o.payload,'$.event_date'),''),'9999-12-31'),o.id",
              'due': "CASE WHEN o.due_date='' THEN 1 ELSE 0 END,o.due_date,o.id"}
    if value('sort', 'match') not in orders:
        raise ValueError('Orden inválido')
    condition = ' AND '.join(where)
    with connect() as c:
        @lru_cache(maxsize=10000)
        def quality(payload, active):
            item = json.loads(payload)
            item['active'] = availability(item, active) == 'En el último lote'
            return assess(item, personal)
        c.create_function('priority', 2, lambda p, a: quality(p, a)['score'])
        for field in ('top', 'matched', 'low_competition'):
            c.create_function('quality_' + field, 2, lambda p, a, field=field: int(quality(p, a)[field]))
        handled = {feed_group(r['payload'], r['duplicate_key'], r['id']) for r in c.execute("SELECT id,payload,duplicate_key FROM opportunities WHERE favorite=1 OR status<>'Sin guardar'")}
        c.create_function('unhandled', 3, lambda payload, key, item_id: int(not handled or feed_group(payload, key, item_id) not in handled))
        c.create_function('feed_group', 3, feed_group)
        c.create_function('local_market', 1, lambda p: local_market(json.loads(p)))
        c.create_function('event_allowed', 1, lambda p: int(eligible_event(json.loads(p))))
        c.create_function('fold', 1, fold)
        c.create_function('geo', 1, lambda p: geo(json.loads(p)))
        c.create_function('available', 2, lambda p, a: int(availability(json.loads(p), a) == 'En el último lote'))
        def score(text, mode, level, location):
            return len(matches_folded(text, personal['skills'])) * 10 + sum(
                5 for key, value in [('mode', mode), ('level', level)] if personal[key] and personal[key] == value
            ) + (5 if personal['location'] and fold(personal['location']) in fold(location) else 0)
        c.create_function('score', 4, score)
        order = orders[value('sort', 'match')]
        cte = 'WITH filtered AS (SELECT o.*,feed_group(o.payload,o.duplicate_key,o.id) AS feed_key FROM opportunities o WHERE ' + condition + ') '
        raw_total = c.execute(cte + 'SELECT COUNT(*) FROM filtered', args).fetchone()[0]
        if grouped:
            total = c.execute(cte + 'SELECT COUNT(DISTINCT feed_key) FROM filtered', args).fetchone()[0]
            sql = cte + ", ranked AS (SELECT o.*,ROW_NUMBER() OVER(PARTITION BY feed_key ORDER BY " + order + ") AS group_rank,COUNT(*) OVER(PARTITION BY feed_key) AS group_count,json_group_array(json_extract(o.payload,'$.location')) OVER(PARTITION BY feed_key) AS group_locations FROM filtered o) SELECT o.* FROM ranked o WHERE group_rank=1"
        else:
            total = raw_total
            sql = cte + "SELECT o.*,1 AS group_count,json_array(json_extract(o.payload,'$.location')) AS group_locations FROM filtered o"
        rows = c.execute(sql + ' ORDER BY ' + order + ' LIMIT ? OFFSET ?', args + [limit, offset]).fetchall()
        items = [decorate(row, personal) for row in rows]
        for item, row in zip(items, rows):
            item['group_count'] = row['group_count']
            item['group_locations'] = list(dict.fromkeys(json.loads(row['group_locations'])))
            item['duplicate_count'] = c.execute("SELECT COUNT(*) FROM opportunities WHERE duplicate_key=? AND id<>? AND duplicate_key<>''", (row['duplicate_key'], row['id'])).fetchone()[0]
    return {'items': items, 'total': total, 'raw_total': raw_total,
            'grouped_duplicates': raw_total - total, 'offset': offset, 'limit': limit,
            'has_more': offset + len(items) < total}



def detail(connect, item_id):
    personal = profile(connect)
    with connect() as c:
        row = c.execute('SELECT * FROM opportunities WHERE id=?', (item_id,)).fetchone()
        if row is None:
            return None
        item = decorate(row, personal, True)
        item['sources'] = [dict(r) for r in c.execute('SELECT source,active,seen FROM sightings WHERE opportunity_id=? ORDER BY source', (item_id,))]
        c.create_function('feed_group', 3, feed_group)
        item['grouped_variants'] = [dict(id=r['id'], url=json.loads(r['payload'])['url'],
                                        source=r['source'], title=json.loads(r['payload'])['title'], status=r['status'], favorite=bool(r['favorite']),
                                        location=json.loads(r['payload']).get('location', ''))
            for r in c.execute('''SELECT * FROM opportunities WHERE
                feed_group(payload,duplicate_key,id)=? ORDER BY id''',
                (feed_group(row['payload'], row['duplicate_key'], row['id']),))]
        item['timeline'] = [dict(r) for r in c.execute('SELECT previous,status,changed FROM stage_history WHERE opportunity_id=? ORDER BY id DESC', (item_id,))]
        if not item['applied_date']:
            from application_analytics import local_date
            first = next((event['changed'] for event in reversed(item['timeline']) if event['status'] == 'Postulada'), '')
            item['applied_date'] = local_date(first)
        item['duplicates'] = [dict(id=r['id'], title=json.loads(r['payload'])['title'],
                                   company=json.loads(r['payload']).get('company', ''),
                                   location=json.loads(r['payload']).get('location', ''))
                              for r in c.execute("SELECT id,payload FROM opportunities WHERE duplicate_key=? AND duplicate_key<>'' AND id<>? ORDER BY id LIMIT 20", (row['duplicate_key'], item_id))]
    return item


def update_tracking(connect, data):
    item_id = data.get('id')
    if not isinstance(item_id, str) or not re.fullmatch(r'[a-f0-9]{24}', item_id):
        raise ValueError('ID inválido')
    changes = {}
    if 'status' in data:
        if data['status'] not in STATES:
            raise ValueError('Estado inválido')
        changes['status'] = data['status']
    if 'favorite' in data:
        if not isinstance(data['favorite'], bool):
            raise ValueError('Favorito debe ser verdadero o falso')
        changes['favorite'] = int(data['favorite'])
    for key, maximum in [('notes', 10000), ('next_action', 500), ('due_date', 10), ('applied_date', 10), ('applied_via', 200)]:
        if key in data:
            if not isinstance(data[key], str) or len(data[key]) > maximum:
                raise ValueError(f'{key}: texto de hasta {maximum} caracteres')
            changes[key] = data[key].strip()
    if 'due_date' in changes:
        valid_date(changes['due_date'])
    if 'applied_date' in changes:
        valid_date(changes['applied_date'])
        if changes['applied_date'] > today():
            raise ValueError('La fecha de postulación no puede estar en el futuro')
    if not changes:
        raise ValueError('No hay cambios de seguimiento')
    with connect() as c:
        previous = c.execute('SELECT status,applied_date FROM opportunities WHERE id=?', (item_id,)).fetchone()
        if previous is None:
            return False
        if changes.get('status') == 'Postulada' and previous['status'] != 'Postulada' and not previous['applied_date'] and 'applied_date' not in changes:
            first = c.execute("SELECT changed FROM stage_history WHERE opportunity_id=? AND status='Postulada' ORDER BY id LIMIT 1", (item_id,)).fetchone()
            from application_analytics import local_date
            changes['applied_date'] = local_date(first['changed']) if first else today()
        if 'status' in changes and changes['status'] != previous['status']:
            c.execute('INSERT INTO stage_history(opportunity_id,previous,status,changed) VALUES(?,?,?,?)',
                      (item_id, previous['status'], changes['status'], now()))
        c.execute('UPDATE opportunities SET ' + ','.join(key + '=?' for key in changes) + ' WHERE id=?', list(changes.values()) + [item_id])
    return True


def backup(connect):
    with connect() as c:
        c.execute('BEGIN')
        personal = c.execute("SELECT value FROM settings WHERE key='profile'").fetchone()
        return {'format': 'careeros', 'version': 1, 'exported': now(),
                'opportunities': [dict(r) for r in c.execute('SELECT * FROM opportunities ORDER BY id')],
                'sightings': [dict(r) for r in c.execute('SELECT * FROM sightings ORDER BY opportunity_id,source')],
                'timeline': [dict(r) for r in c.execute('SELECT opportunity_id,previous,status,changed FROM stage_history ORDER BY id')],
                'profile': json.loads(personal['value']) if personal else dict(DEFAULT_PROFILE)}


def validate_backup(data, valid_url):
    if not isinstance(data, dict) or data.get('format') != 'careeros' or type(data.get('version')) is not int or data['version'] != 1:
        raise ValueError('Respaldo incompatible; utiliza una exportación CareerOS versión 1')
    validate_profile(data.get('profile'))
    rows, sightings, timeline = (data.get(k) for k in ('opportunities', 'sightings', 'timeline'))
    if not all(isinstance(v, list) for v in (rows, sightings, timeline)) or len(rows) > 100000 or len(sightings) > 500000 or len(timeline) > 500000:
        raise ValueError('Estructura o tamaño del respaldo inválidos')
    ids = set()
    def check_payload(payload, item_id, source):
        if not isinstance(payload, str) or len(payload) > 1000000:
            raise ValueError('Anuncio inválido en respaldo')
        item = json.loads(payload)
        if not isinstance(item, dict):
            raise ValueError('Anuncio inválido en respaldo')
        for key in ('title', 'company', 'location', 'description', 'url', 'source', 'mode', 'kind', 'salary', 'published', 'level'):
            if not isinstance(item.get(key), str):
                raise ValueError(f'Campo inválido en respaldo: {key}')
        if not item['title'].strip() or not valid_url(item['url']) or item.get('id') != item_id or hashlib.sha256(item['url'].encode()).hexdigest()[:24] != item_id or item['source'] != source:
            raise ValueError('Identidad o enlace inválidos en respaldo')
        if item.get('apply_url') and not valid_url(item['apply_url']):
            raise ValueError('Enlace de postulación inválido')
        if item.get('expires') is not None and (type(item['expires']) not in (int, float) or not 0 <= item['expires'] < 253402300800):
            raise ValueError('Expiración inválida')
        if not isinstance(item.get('skills'), list) or not all(isinstance(s, str) for s in item['skills']):
            raise ValueError('Habilidades inválidas')
        if not isinstance(item.get('timezones', []), list) or not all(type(z) in (int, float) for z in item.get('timezones', [])):
            raise ValueError('Zonas horarias inválidas')
        for key in ('contact_name','contact_email','contact_phone','contact_url','contact_note','client_location','project_type',
                    'project_deadline','requirements','deliverables','event_type','event_period','event_end_date',
                    'registration_deadline','submission_deadline','registration_url','venue','cost','prizes','description_scope','summary'):
            if key in item and (not isinstance(item[key],str) or len(item[key])>20000):
                raise ValueError(f'Campo de oportunidad inválido: {key}')
        for key in ('contact_url','registration_url'):
            if item.get(key) and not valid_url(item[key]):
                raise ValueError('Enlace de contacto o inscripción inválido')
        for key in ('project_deadline','event_end_date','registration_deadline','submission_deadline'):
            if item.get(key): valid_date(item[key])
        for key in ('required_skills','topics'):
            if key in item and (not isinstance(item[key],list) or len(item[key])>100 or not all(isinstance(v,str) and len(v)<=200 for v in item[key])):
                raise ValueError('Temáticas o requisitos inválidos')
        return item
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not re.fullmatch('[a-f0-9]{24}', row['id']) or row['id'] in ids:
            raise ValueError('IDs inválidos o repetidos en respaldo')
        ids.add(row['id'])
        for key, maximum in [('source', 200), ('seen', 100), ('notes', 10000), ('next_action', 500), ('due_date', 10)]:
            if not isinstance(row.get(key), str) or len(row[key]) > maximum:
                raise ValueError(f'Campo inválido en respaldo: {key}')
        if row.get('status') not in STATES or type(row.get('favorite')) is not int or row['favorite'] not in (0, 1) or type(row.get('active')) is not int or row['active'] not in (0, 1):
            raise ValueError('Seguimiento inválido en respaldo')
        for field, maximum in [('applied_date', 10), ('applied_via', 200)]:
            if not isinstance(row.get(field, ''), str) or len(row.get(field, '')) > maximum:
                raise ValueError('Datos de postulación inválidos en respaldo')
        valid_date(row.get('applied_date', ''))
        valid_date(row['due_date'])
        check_payload(row.get('payload'), row['id'], row['source'])
    seen = set()
    for row in sightings:
        if not isinstance(row, dict) or row.get('opportunity_id') not in ids or not isinstance(row.get('source'), str) or not 1 <= len(row['source']) <= 200 or type(row.get('active')) is not int or row['active'] not in (0, 1) or not isinstance(row.get('seen'), str) or len(row['seen']) > 100:
            raise ValueError('Procedencia inválida en respaldo')
        key = row['opportunity_id'], row['source']
        if key in seen:
            raise ValueError('Procedencia repetida en respaldo')
        seen.add(key)
        check_payload(row.get('payload'), row['opportunity_id'], row['source'])
    if any((row['id'], row['source']) not in seen for row in rows):
        raise ValueError('Falta la fuente original de un anuncio')
    for row in timeline:
        if not isinstance(row, dict) or row.get('opportunity_id') not in ids or row.get('previous') not in STATES or row.get('status') not in STATES or not isinstance(row.get('changed'), str) or len(row['changed']) > 100:
            raise ValueError('Historial inválido en respaldo')
    return data


def restore_preview(connect, data, valid_url):
    validate_backup(data, valid_url)
    with connect() as c:
        existing = {r['id'] for r in c.execute('SELECT id FROM opportunities')}
    incoming = {r['id'] for r in data['opportunities']}
    return {'new': len(incoming - existing), 'updated': len(incoming & existing),
            'preserved': len(existing - incoming), 'total': len(existing | incoming)}


def restore(connect, db_path, data, valid_url):
    preview = restore_preview(connect, data, valid_url)
    # SQLite's online backup API makes a consistent copy before changing data.
    import sqlite3
    target = Path(db_path).parent / 'backups' / ('before-restore-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.db')
    target.parent.mkdir(parents=True, exist_ok=True)
    with connect() as c, closing(sqlite3.connect(target)) as destination:
        c.backup(destination)
    with connect() as c:
        for row in data['opportunities']:
            item = json.loads(row['payload'])
            keys = ['id', 'source', 'payload', 'active', 'seen', 'status', 'notes', 'favorite', 'next_action', 'due_date']
            keys += ['applied_date', 'applied_via']
            values = [row.get(k, '') for k in keys] + [search_text(item), duplicate_key(item)]
            c.execute('INSERT INTO opportunities(' + ','.join(keys + ['search_text', 'duplicate_key']) + ') VALUES(' + ','.join('?' for _ in values) + ') ON CONFLICT(id) DO UPDATE SET ' + ','.join(k + '=excluded.' + k for k in keys[1:] + ['search_text', 'duplicate_key']), values)
            c.execute('DELETE FROM sightings WHERE opportunity_id=?', (row['id'],))
            c.execute('DELETE FROM stage_history WHERE opportunity_id=?', (row['id'],))
        for row in data['sightings']:
            c.execute('INSERT INTO sightings VALUES(?,?,?,?,?)', tuple(row[k] for k in ('opportunity_id', 'source', 'payload', 'active', 'seen')))
        for row in data['timeline']:
            c.execute('INSERT INTO stage_history(opportunity_id,previous,status,changed) VALUES(?,?,?,?)', tuple(row[k] for k in ('opportunity_id', 'previous', 'status', 'changed')))
        c.execute("INSERT OR REPLACE INTO settings VALUES('profile',?)", (json.dumps(validate_profile(data['profile'])),))
        c.execute('''UPDATE opportunities SET active=EXISTS(SELECT 1 FROM sightings s
            WHERE s.opportunity_id=opportunities.id AND s.active=1)''')
    return dict(preview, safety_backup=str(target))


def acquire_operation(db_path):
    """OS advisory lock; released even if a CLI/server process crashes."""
    handle = open(str(db_path) + '.operation.lock', 'a+b')
    try:
        if __import__('os').name == 'nt':
            import msvcrt
            handle.seek(0)
            if not handle.read(1):
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except (BlockingIOError, OSError):
        handle.close()
        return None


def release_operation(handle):
    if handle is not None:
        handle.close()
