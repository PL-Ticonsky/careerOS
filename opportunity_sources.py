"""Public project and event adapters. Import facts, never infer hidden contacts."""
import re
from datetime import date, datetime, timezone
from urllib.parse import urlencode, urlparse, quote


def safe_url(value, valid_url, domain=None):
    if not isinstance(value, str) or not valid_url(value):
        return ''
    host = urlparse(value).hostname
    if domain and host != domain and not host.endswith('.' + domain):
        return ''
    return value


def number(value):
    if type(value) not in (int, float) or not 0 <= value < 1e12:
        return ''
    return f'{value:g}'


def freelancer_record(source, row, normalize, valid_url):
    if not isinstance(row, dict) or 'status' not in row:
        raise ValueError('Proyecto sin estado publicado')
    if row.get('deleted') or row.get('nonpublic') or row.get('frontend_project_status') not in (None, 'open'):
        return None
    if row.get('status') != 'active':
        return None
    slug = row.get('seo_url')
    if not isinstance(slug, str) or not re.fullmatch(r'[\w/-]+', slug):
        raise ValueError('Enlace público de proyecto inválido')
    url = 'https://www.freelancer.com/projects/' + slug
    owner = row.get('_owner') or row.get('owner_info') or {}
    name = owner.get('display_name') or owner.get('public_name') or owner.get('username') or ''
    if not isinstance(name, str):
        name = ''
    currency = (row.get('currency') or {}).get('code') or ''
    budget = row.get('budget') or {}
    low, high = number(budget.get('minimum')), number(budget.get('maximum'))
    project_type = {'fixed': 'Precio fijo', 'hourly': 'Por hora'}.get(row.get('type'), 'Por confirmar')
    amount = (f'{low or "?"}–{high or "?"} {currency} · {project_type}' if low or high else '')
    location = row.get('location') or {}
    project_location = ', '.join(str(v) for v in [location.get('city'), (location.get('country') or {}).get('name')] if v)
    client_location = ', '.join(str(v) for v in [owner.get('city'), (owner.get('country') or {}).get('name')] if v)
    local = row.get('local')
    mode = 'Presencial' if local is True else 'Remoto' if local is False else 'Por confirmar'
    # Employer country is not a restriction on where a remote freelancer lives.
    if not local:
        project_location = 'Remoto · país de contratación por confirmar'
    skills = [j['name'] for j in row.get('jobs', []) if isinstance(j, dict) and isinstance(j.get('name'), str)]
    description = row.get('description') or row.get('preview_description') or ''
    item = normalize(source['id'], row['title'], name, project_location, url, description,
                     amount, datetime.fromtimestamp(row['submitdate'], timezone.utc).isoformat()
                     if row.get('submitdate') else '', mode, kind='freelance')
    username = owner.get('username')
    profile_url = 'https://www.freelancer.com/u/' + quote(username, safe='') if isinstance(username, str) and re.fullmatch(r'[A-Za-z0-9_-]+', username) else ''
    item.update(contact_name=name, contact_email='', contact_url=profile_url or url,
                contact_channel='Freelancer', contact_note='Contacto y propuestas dentro de Freelancer. El catálogo público no facilita el correo del cliente; puede requerir una cuenta.',
                client_location=client_location, project_type=project_type, requirements='', deliverables='',
                required_skills=skills, description_scope='full' if row.get('description') else 'summary',
                summary=re.sub(r'\s+', ' ', item['description']).strip()[:320],
                bid_count=(row.get('bid_stats') or {}).get('bid_count'),
                payment_verified=(owner.get('status') or {}).get('payment_verified'),
                project_deadline='', apply_url=url)
    return item


MONTHS = {name: index for index, name in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], 1)}


def event_dates(period):
    """Parse Devpost's human calendar ranges without inventing a timezone/time."""
    pattern = r'(?:(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+)?(\d{1,2})(?:,\s*(\d{4}))?'
    parts = re.split(r'\s+[–-]\s+', period.strip())
    if len(parts) not in (1, 2):
        return '', ''
    found = [re.fullmatch(pattern, part.strip()) for part in parts]
    if not all(found) or not found[0][1]:
        return '', ''
    start, end = found[0], found[-1]
    last_year = end[3] or start[3]
    if not last_year:
        return '', ''
    first_month, last_month = MONTHS[start[1]], MONTHS[end[1] or start[1]]
    first_year = int(start[3] or last_year)
    if not start[3] and first_month > last_month:
        first_year -= 1
    try:
        first = date(first_year, first_month, int(start[2]))
        last = date(int(last_year), last_month, int(end[2]))
        return (first.isoformat(), last.isoformat()) if first <= last else ('', '')
    except ValueError:
        return '', ''


def event_mode(location):
    text = location.lower()
    online = re.search(r'\b(online|virtual|remote|remoto)\b', text)
    if re.search(r'\b(hybrid|hibrido|híbrido)\b', text) or (online and re.search(r'\b(in.person|presencial)\b', text)):
        return 'Híbrido'
    return 'Remoto' if online else 'Presencial' if location else 'Por confirmar'


def devpost_record(source, row, normalize, valid_url, plain):
    if not isinstance(row, dict) or 'open_state' not in row:
        raise ValueError('Convocatoria sin estado publicado')
    if row.get('open_state') != 'open' or row.get('invite_only'):
        return None
    url = safe_url(row['url'], valid_url, 'devpost.com')
    if not url:
        raise ValueError('Enlace de convocatoria inválido')
    location = (row.get('displayed_location') or {}).get('location') or ''
    mode = event_mode(location)
    period = row.get('submission_period_dates') or ''
    start, end = event_dates(period)
    themes = [theme['name'] for theme in row.get('themes', []) if isinstance(theme, dict) and isinstance(theme.get('name'), str)]
    organizer = row.get('organization_name') or ''
    if organizer.lower() in ('nill', 'null', 'none'):
        organizer = ''
    prize = re.sub(r'([$€£₹¥])\s+(?=\d)', r'\1', plain(row.get('prize_amount', '')))
    description = row.get('description') or '\n\n'.join(part for part in [
        row['title'], 'Organizador: ' + organizer if organizer else '',
        'Temáticas: ' + ', '.join(themes) if themes else '',
        'Período de participación publicado: ' + period if period else '',
        'Premios publicados: ' + prize if prize else '',
    ] if part)
    # A prize is not an attendance fee; keep those fields separate.
    item = normalize(source['id'], row['title'], organizer, location, url,
                     description=description, mode=mode, kind='evento', event_date=start)
    item.update(event_end_date=end, event_period=period, submission_deadline=end, registration_deadline='',
                event_type='Hackatón', topics=themes, prizes=prize, cost='',
                participants=row.get('registrations_count'),
                contact_name=organizer, contact_email='', contact_url=url, contact_channel='Devpost',
                contact_note='Consulta el contacto del organizador o la sección Discussion del evento en Devpost. El catálogo no publica su correo.',
                requirements='', deliverables='', description_scope='full' if row.get('description') else 'summary',
                summary=' · '.join(themes),
                apply_url=safe_url(row.get('start_a_submission_url'), valid_url, 'devpost.com') or url,
                registration_url=url)
    return item


def collect(source, fetch, normalize, valid_url, plain, batch_class, sleep):
    provider = source['provider']
    batch = batch_class()
    seen = set()
    pages = source.get('max_pages', 2 if provider == 'freelancer' else 7)
    if type(pages) is not int or not 1 <= pages <= 10:
        raise ValueError('max_pages debe estar entre 1 y 10')

    def consume(rows, owners=None):
        if not isinstance(rows, list):
            raise ValueError('La fuente no devolvió una lista')
        for index, row in enumerate(rows):
            try:
                if provider == 'freelancer':
                    if owners and row.get('owner_id') is not None:
                        row = dict(row, _owner=owners.get(str(row['owner_id'])) or row.get('owner_info'))
                    item = freelancer_record(source, row, normalize, valid_url)
                else:
                    item = devpost_record(source, row, normalize, valid_url, plain)
                if item is not None and item['id'] not in seen:
                    seen.add(item['id']); batch.append(item)
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError, OSError) as exc:
                batch.rejected.append({'record': index, 'error': type(exc).__name__})

    if provider == 'freelancer':
        queries = source.get('queries', ['python', 'javascript', 'backend'])
        if not isinstance(queries, list) or not 1 <= len(queries) <= 5 or any(not isinstance(q, str) or not 1 <= len(q) <= 80 for q in queries):
            raise ValueError('Consultas de proyectos inválidas')
        for query in queries:
            for page in range(pages):
                params = dict(query=query, limit=50, offset=page*50, full_description='true',
                              job_details='true', user_details='true', user_display_info='true',
                              owner_info='true', compact='false')
                data = fetch('https://www.freelancer.com/api/projects/0.1/projects/active/?' + urlencode(params))
                if data.get('status') != 'success':
                    raise ValueError('Freelancer no pudo consultar los proyectos')
                result = data['result']; rows = result['projects']
                consume(rows, result.get('users') or {})
                if len(rows) < 50:
                    break
                if page + 1 < pages:
                    sleep(1.1)
    elif provider == 'devpost':
        for page in range(1, pages + 1):
            data = fetch('https://devpost.com/api/hackathons?' + urlencode({'status[]': 'open', 'page': page}))
            rows = data['hackathons']; consume(rows)
            metadata = data.get('meta') or {}
            if type(metadata.get('total_count')) is not int or type(metadata.get('per_page')) is not int or metadata['total_count'] < 0 or metadata['per_page'] < 1:
                raise ValueError('La paginación de Devpost no es válida')
            if not rows or page * metadata['per_page'] >= metadata['total_count']:
                break
            if page < pages:
                sleep(1.1)
    else:
        raise ValueError('Proveedor de oportunidades no implementado')
    if batch.rejected and not batch:
        raise ValueError('Todos los registros de la fuente fueron rechazados')
    return batch
