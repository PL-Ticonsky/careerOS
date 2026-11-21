"""Bounded, read-only connectors for public jobs and credentialed Jooble search."""
import json
import os
from pathlib import Path
import re
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


def posted(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    return str(value or '')


def public_url(value, valid_url, host):
    if not valid_url(value):
        raise ValueError('Enlace público inválido')
    hostname = urlparse(value).hostname
    if hostname != host and not hostname.endswith('.' + host):
        raise ValueError('El enlace no pertenece a la fuente')
    return value


def getonbrd_record(source, row, normalize, valid_url):
    a = row['attributes']
    company = a.get('company', {}).get('data') or {}
    company_name = (company.get('attributes') or {}).get('name', '')
    locations = []
    for city in (a.get('location_cities') or {}).get('data', []):
        fields = city.get('attributes') or {}
        locations.append(', '.join(str(fields[k]) for k in ('name', 'country') if fields.get(k)))
    countries = a.get('countries') or []
    if not isinstance(countries, list) or not all(isinstance(c, str) for c in countries):
        raise ValueError('Países inválidos')
    locations.extend(countries)
    modality = a.get('remote_modality')
    mode = {'hybrid': 'Híbrido', 'no_remote': 'Presencial',
            'remote_local': 'Remoto', 'remote_worldwide': 'Remoto'}.get(modality, 'Remoto' if a.get('remote') is True else 'Por confirmar')
    # Only the explicit worldwide modality grants a worldwide signal; remote_local
    # and the word "Remote" never invent Colombian eligibility.
    if modality == 'remote_worldwide':
        locations.append('Worldwide')
    description = '\n\n'.join(str(a[k]) for k in ('projects', 'functions_headline', 'functions',
        'description_headline', 'description', 'desirable_headline', 'desirable', 'benefits_headline', 'benefits') if a.get(k))
    low, high = a.get('min_salary'), a.get('max_salary')
    salary = f'{low if low is not None else "?"}–{high if high is not None else "?"} · moneda y período por confirmar' if low is not None or high is not None else ''
    item = normalize(source['id'], a['title'], company_name, ' · '.join(dict.fromkeys(x for x in locations if x)),
        public_url(row['links']['public_url'], valid_url, 'getonbrd.com'), description, salary,
        posted(a.get('published_at')), mode)
    item.update(refresh_before=time.time() + 86400, salary_min=low, salary_max=high,
                provider_id=str(row['id']), employment_type=(a.get('modality', {}).get('data', {}).get('attributes') or {}).get('name', ''))
    company_url = company.get('links', {}).get('public_url')
    if not company_url and company.get('id'):
        company_url = 'https://www.getonbrd.com/companies/' + quote(str(company['id']), safe='')
    if company_url:
        item['company_url'] = public_url(company_url, valid_url, 'getonbrd.com')
    return item


def smartrecruiters_record(source, row, normalize, valid_url):
    if row.get('visibility') != 'PUBLIC' or row.get('active') is False:
        return None
    loc = row.get('location') or {}
    country = 'Colombia' if str(loc.get('country', '')).lower() == 'co' else str(loc.get('country', ''))
    full_location = loc.get('fullLocation') or ''
    location = full_location if re.search(r'\w', full_location) else ', '.join(x for x in (loc.get('city', ''), country) if x)
    # Country code is authoritative even when fullLocation omits the country name.
    if country == 'Colombia' and 'colombia' not in location.lower():
        location += ', Colombia'
    mode = 'Híbrido' if loc.get('hybrid') is True else 'Remoto' if loc.get('remote') is True else 'Por confirmar'
    sections = (row.get('jobAd') or {}).get('sections') or {}
    description = '\n\n'.join(str(section.get('title', '')) + '\n' + str(section.get('text', ''))
        for section in sections.values() if isinstance(section, dict))
    item = normalize(source['id'], row['name'], row['company']['name'], location,
        public_url(row['postingUrl'], valid_url, 'smartrecruiters.com'), description,
        published=posted(row.get('releasedDate')), mode=mode)
    item.update(apply_url=item['url'], company_url=source.get('company_url', source.get('url', '')), employment_type=(row.get('typeOfEmployment') or {}).get('label', ''),
                description_scope='full' if description else 'summary')
    return item


def jooble_key(db=None):
    environment = os.environ.get('JOOBLE_API_KEY', '').strip()
    if environment or db is None:
        return environment
    path = Path(db).parent / 'jooble-private.json'
    try:
        value = json.loads(path.read_text()).get('key', '')
    except (OSError, ValueError, AttributeError):
        return ''
    return value.strip() if isinstance(value, str) else ''


def jooble_search(payload, key=None):
    key = jooble_key() if key is None else key
    if not key:
        raise ValueError('Falta la clave de Jooble Colombia. Solicítala en co.jooble.org/api/about y configura JOOBLE_API_KEY en el servidor.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,200}', key):
        raise ValueError('La clave de Jooble no tiene un formato válido')
    request = Request('https://co.jooble.org/api/' + key, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json', 'User-Agent': 'CareerOS personal reader/1.0'})
    try:
        with urlopen(request, timeout=25) as response:
            return json.load(response)
    except HTTPError as exc:
        raise ValueError(f'Jooble Colombia devolvió HTTP {exc.code}. Comprueba la clave regional y la cuota.') from None
    except (URLError, TimeoutError):
        raise ValueError('Jooble Colombia no respondió. Intenta de nuevo.') from None


def collect(source, fetch, normalize, valid_url, batch_class, local_market, sleep, key=None):
    provider = source['provider']
    pages = source.get('max_pages', 3)
    if type(pages) is not int or not 1 <= pages <= 10:
        raise ValueError('max_pages debe estar entre 1 y 10')
    batch = batch_class()
    seen = set()

    def consume(rows, parser):
        if not isinstance(rows, list):
            raise ValueError('La fuente no devolvió una lista de ofertas')
        for index, row in enumerate(rows):
            try:
                item = parser(row)
                if item and local_market(item) >= 2 and item['id'] not in seen:
                    seen.add(item['id']); batch.append(item)
            except (ValueError, KeyError, TypeError, AttributeError, OverflowError, OSError):
                batch.rejected.append({'record': index, 'error': 'Anuncio incompleto'})

    if provider == 'getonbrd':
        signatures = set()
        for page in range(1, pages + 1):
            params = [('country_code', 'co'), ('per_page', 120), ('page', page), ('lang', 'es')]
            params.extend(('expand[]', name) for name in ('company', 'location_cities', 'modality', 'seniority'))
            data = fetch('https://www.getonbrd.com/api/v0/search/jobs?' + urlencode(params))
            rows = data['data']
            if not isinstance(rows, list):
                raise ValueError('Respuesta de Get on Board inválida')
            signature = json.dumps([row.get('id') for row in rows if isinstance(row, dict)])
            if rows and signature in signatures:
                raise ValueError('Get on Board repitió una página')
            signatures.add(signature)
            consume(rows, lambda row: getonbrd_record(source, row, normalize, valid_url))
            total_pages = data['meta']['total_pages']
            if type(total_pages) is not int or total_pages < 0:
                raise ValueError('Paginación de Get on Board inválida')
            if not rows or page >= total_pages:
                break
            if page < pages: sleep(0.3)
    elif provider == 'smartrecruiters':
        board = source['board']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', board):
            raise ValueError('Identificador de empresa inválido')
        base = f'https://api.smartrecruiters.com/v1/companies/{board}/postings'
        imported = set()
        for page in range(pages):
            offset = page * 100
            query = {'limit': 100, 'offset': offset}
            if source.get('country_filter', True):
                query['country'] = 'co'
            data = fetch(base + '?' + urlencode(query))
            rows, total = data['content'], data['totalFound']
            if not isinstance(rows, list) or type(total) is not int or total < 0:
                raise ValueError('Respuesta de SmartRecruiters inválida')
            for row in rows:
                # Fetch only public listings; construct a fixed-host detail URL.
                if row.get('visibility') != 'PUBLIC': continue
                if not source.get('country_filter', True) and (row.get('location') or {}).get('country', '').lower() != 'co': continue
                identifier = str(row['id'])
                if not re.fullmatch(r'[A-Za-z0-9_-]+', identifier):
                    batch.rejected.append({'error': 'ID inválido'}); continue
                detail = fetch(base + '/' + identifier)
                consume([detail], lambda row: smartrecruiters_record(source, row, normalize, valid_url))
                imported.add(identifier)
                sleep(0.1)
            if not rows or offset + len(rows) >= total: break
            if page + 1 < pages: sleep(0.3)
        for identifier in source.get('seed_postings', []):
            if not re.fullmatch(r'[A-Za-z0-9_-]+', str(identifier)):
                raise ValueError('Identificador de publicación inválido')
            if str(identifier) not in imported:
                detail = fetch(base + '/' + str(identifier))
                consume([detail], lambda row: smartrecruiters_record(source, row, normalize, valid_url))
        if source.get('partial_catalog'):
            batch.partial = True
    elif provider == 'jooble':
        queries = source.get('queries', ['desarrollador', 'python', 'datos'])
        if not isinstance(queries, list) or not 1 <= len(queries) <= 5 or not all(isinstance(q, str) and 1 <= len(q) <= 100 for q in queries):
            raise ValueError('Consultas de Jooble inválidas')
        for query in queries:
            for page in range(1, pages + 1):
                data = jooble_search({'keywords': query, 'location': 'Bogotá, Colombia', 'radius': '0',
                    'page': str(page), 'ResultOnPage': 20}, key=key)
                rows = data['jobs']
                def parse(row):
                    return normalize(source['id'], row['title'], row.get('company', ''), row.get('location', ''),
                        row['link'], row.get('snippet', ''), row.get('salary', ''), row.get('updated', ''))
                consume(rows, parse)
                if not rows or len(rows) < 20: break
                if page < pages: sleep(0.5)
    else:
        raise ValueError('Proveedor no implementado')
    if batch.rejected and not batch:
        raise ValueError(f'Todos los registros fueron rechazados: {len(batch.rejected)}')
    return batch
