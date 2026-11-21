"""Bounded readers of public employer pages; never submit applications."""
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.error import URLError

from discovery import Page, objects, read_page
from career_rules import fold


class TeamtailorDetail(HTMLParser):
    """Visible job body and labeled facts when a site omits JobPosting markup."""
    def __init__(self, text):
        super().__init__()
        self.title = ''
        self.in_title = False
        self.depth = 0
        self.body = []
        self.field = None
        self.label = ''
        self.facts = {}
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'h1' and not self.title:
            self.in_title = True
        if tag in ('dt', 'dd'):
            self.field = tag
            if tag == 'dt':
                self.label = ''
        if tag == 'div':
            if self.depth:
                self.depth += 1
            elif not self.body and attrs.get('data-controller') == 'careersite--responsive-video':
                self.depth = 1
        if self.depth:
            self.body.append(self.get_starttag_text())

    def handle_data(self, text):
        if self.in_title:
            self.title += text
        if self.field == 'dt':
            self.label += text
        if self.field == 'dd':
            key = fold(self.label.strip())
            self.facts[key] = self.facts.get(key, '') + text
        if self.depth:
            self.body.append(text)

    def handle_endtag(self, tag):
        if tag == 'h1':
            self.in_title = False
        if tag in ('dt', 'dd'):
            self.field = None
        if self.depth:
            self.body.append('</' + tag + '>')
            if tag == 'div':
                self.depth -= 1

    def record(self, source, url, normalize):
        location = (self.facts.get('ubicaciones') or self.facts.get('locations') or '').strip()
        if not self.title.strip() or not location or not self.body:
            raise ValueError('El detalle no contiene título, ubicación y descripción verificables')
        remote = fold(self.facts.get('estado remoto', self.facts.get('remote status', '')))
        mode = 'Híbrido' if 'hibrid' in remote or 'hybrid' in remote else 'Remoto' if 'remoto' in remote or 'remote' in remote else ''
        item = normalize(source['id'], self.title.strip(), source['company'], location, url,
                         ''.join(self.body), mode=mode)
        item.update(apply_url=url, company_url=source.get('company_url', source['url']),
                    employment_type=(self.facts.get('tipo de empleo') or self.facts.get('employment type') or '').strip(),
                    description_scope='full')
        return item


def trusted(url, hosts, valid_url):
    if not valid_url(url) or urlparse(url).hostname not in hosts:
        raise ValueError('El enlace no pertenece al portal de contratación')
    return url


def locations(value):
    if not isinstance(value, list):
        value = [value]
    result = []
    for row in value:
        if isinstance(row, str):
            result.append('Colombia' if row.upper() == 'CO' else row)
        elif isinstance(row, dict):
            if row.get('@type') in ('Country', 'AdministrativeArea') and row.get('name'):
                result.append('Colombia' if str(row['name']).upper() == 'CO' else str(row['name']))
                continue
            address = row.get('address', row)
            if not isinstance(address, dict):
                continue
            country = address.get('addressCountry', address.get('country', ''))
            if isinstance(country, dict):
                country = country.get('name', '')
            country = 'Colombia' if str(country).upper() == 'CO' else country
            result.append(', '.join(str(x) for x in [address.get('addressLocality', address.get('city', '')),
                address.get('addressRegion', address.get('region', '')), country] if x))
    return ' · '.join(dict.fromkeys(filter(None, result)))


def structured_job(source, row, url, normalize, valid_url):
    hosts = source['allowed_hosts']
    location = locations(row.get('jobLocation', []))
    remote = 'TELECOMMUTE' in str(row.get('jobLocationType', ''))
    if remote:
        restrictions = locations(row.get('applicantLocationRequirements', []))
        if restrictions:
            # Explicit applicant restrictions take precedence over office locations.
            location = restrictions
        elif not location:
            location = 'Remoto · país de contratación por confirmar'
    salary = row.get('baseSalary') or {}
    if not isinstance(salary, dict):
        salary = {}
    amount = salary.get('value') or {}
    if not isinstance(amount, dict):
        amount = {'value': amount}
    salary_text = ''
    if any(amount.get(k) is not None for k in ('value', 'minValue', 'maxValue')):
        salary_text = f"{amount.get('value') or str(amount.get('minValue', '?')) + '–' + str(amount.get('maxValue', '?'))} {salary.get('currency', '')} / {amount.get('unitText') or 'período por confirmar'}"
    item = normalize(source['id'], row['title'], source['company'], location,
        trusted(url, hosts, valid_url), row.get('description', ''), salary_text,
        row.get('datePosted', ''), 'Remoto' if remote else '')
    item.update(apply_url=url, company_url=source.get('company_url', source['url']),
                employment_type=row.get('employmentType', ''), description_scope='full')
    if row.get('validThrough'):
        expiry = datetime.fromisoformat(str(row['validThrough']).replace('Z', '+00:00'))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        item['expires'] = expiry.timestamp()
    return item


class DataPage(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.props = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('data-page'):
            data = json.loads(attrs['data-page'])
            if data.get('component') == 'WaasShowJobsPage':
                self.props = data.get('props')


def collect(source, fetch, normalize, valid_url, batch_class, local_market, sleep=time.sleep):
    batch = batch_class()
    seen = set()

    def add(item):
        # Regional remote jobs may be imported when LATAM is explicitly published.
        if item and local_market(item) >= (1 if source.get('include_compatible_remote') else 2) and item['id'] not in seen:
            batch.append(item)
            seen.add(item['id'])

    def parse_detail(url):
        trusted(url, source['allowed_hosts'], valid_url)
        text = read_page(url)
        page = Page(text)
        rows = [row for row in objects(page.blocks) if row.get('@type') == 'JobPosting']
        if not rows:
            if source['provider'] == 'teamtailor_web':
                add(TeamtailorDetail(text).record(source, url, normalize))
                return
            raise ValueError('El detalle no contiene una vacante estructurada verificable')
        for row in rows:
            add(structured_job(source, row, url, normalize, valid_url))

    provider = source['provider']
    if provider == 'teamtailor_web':
        pending = [source['url']]
        visited = set()
        detail_urls = []
        max_pages = source.get('max_pages', 5)
        while pending and len(visited) < max_pages:
            url = pending.pop(0)
            trusted(url, source['allowed_hosts'], valid_url)
            if url in visited:
                continue
            visited.add(url)
            page = Page(read_page(url))
            for href in page.links:
                link = urljoin(url, href)
                if urlparse(link).hostname not in source['allowed_hosts']:
                    continue
                if re.fullmatch(r'/jobs/\d+-[^/]+', urlparse(link).path):
                    link = link.split('?')[0].split('#')[0]
                    if link not in detail_urls:
                        detail_urls.append(link)
                elif urlparse(link).path == '/jobs' and re.fullmatch(r'page=\d+', urlparse(link).query):
                    if link not in visited and link not in pending:
                        pending.append(link)
        if not detail_urls:
            raise ValueError('No se encontraron enlaces de vacantes; comprobar el formato del portal')
        if pending or len(detail_urls) > source.get('max_jobs', 120):
            batch.rejected.append({'error': 'Catálogo limitado por el máximo de páginas o vacantes'})
        for url in detail_urls[:source.get('max_jobs', 120)]:
            try:
                parse_detail(url)
            except (ValueError, KeyError, TypeError) as exc:
                batch.rejected.append({'error': type(exc).__name__})
            sleep(0.1)
    elif provider == 'recruitee_public':
        # This public career-site endpoint was verified without a credential.
        # If authentication becomes mandatory, fail and retain prior observations.
        data = fetch(source['url'].rstrip('/') + '/api/offers/')
        rows = data['offers']
        if not isinstance(rows, list):
            raise ValueError('Catálogo de ofertas inválido')
        for row in rows:
            try:
                if row.get('status') != 'published':
                    continue
                loc = locations(row.get('locations', [])) or locations(row)
                body = row.get('description') or (row.get('translations', {}).get('es') or {}).get('description', '')
                salary = row.get('salary') or {}
                amount = f"{salary.get('min') or '?'}–{salary.get('max') or '?'} {salary.get('currency') or ''} / {salary.get('period') or 'período por confirmar'}" if salary.get('min') or salary.get('max') else ''
                item = normalize(source['id'], row['title'], source['company'], loc,
                    trusted(row['careers_url'], source['allowed_hosts'], valid_url), body, amount,
                    row.get('published_at', ''), 'Híbrido' if row.get('hybrid') else 'Remoto' if row.get('remote') else 'Presencial' if row.get('on_site') else '')
                item.update(apply_url=trusted(row['careers_apply_url'], source['allowed_hosts'], valid_url),
                    company_url=source.get('company_url', source['url']), employment_type=row.get('employment_type_code', ''))
                add(item)
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                batch.rejected.append({'error': type(exc).__name__})
    elif provider == 'workable_public':
        data = fetch(f"https://apply.workable.com/api/v1/widget/accounts/{source['board']}")
        rows = data['jobs']
        if not isinstance(rows, list):
            raise ValueError('Catálogo de Workable inválido')
        for row in rows:
            try:
                loc = locations(row.get('locations', [])) or locations(row)
                item = normalize(source['id'], row['title'], source['company'], loc,
                    trusted(row['url'], source['allowed_hosts'], valid_url),
                    row.get('description', ''), published=row.get('published_on', ''),
                    mode='Remoto' if row.get('telecommuting') else '')
                if local_market(item) < 2:
                    continue
                if item['id'] in seen:
                    continue
                # The widget is a summary; the public detail carries the full role.
                try:
                    page = Page(read_page(item['url']))
                    structured = [j for j in objects(page.blocks) if j.get('@type') == 'JobPosting']
                    if structured:
                        full = structured_job(source, structured[0], item['url'], normalize, valid_url)
                        full['location'] = loc
                        item = full
                except (ValueError, KeyError, TypeError, URLError, TimeoutError):
                    batch.rejected.append({'error': 'Detalle incompleto'})
                item.update(apply_url=trusted(row['application_url'], source['allowed_hosts'], valid_url),
                            company_url=source.get('company_url', source['url']),
                            description_scope='full' if item['description'] else 'summary')
                add(item)
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                batch.rejected.append({'error': type(exc).__name__})
    elif provider == 'yc_public':
        props = DataPage(read_page(source['url'])).props
        if not isinstance(props, dict) or not isinstance(props.get('jobPostings'), list):
            raise ValueError('El catálogo de YC cambió de formato')
        company = props.get('company') or {}
        if company.get('slug') != source['board']:
            raise ValueError('El catálogo no corresponde a la empresa configurada')
        for row in props['jobPostings']:
            try:
                url = trusted(urljoin(source['url'], row['url']), source['allowed_hosts'], valid_url)
                # YC uses ISO country codes in its published location list.
                loc = re.sub(r'(?<!\w)CO(?!\w)', 'Colombia', row.get('location', ''))
                mode = 'Remoto' if re.search(r'\bremote\b', loc, re.I) else ''
                stub = normalize(source['id'], row['title'], source['company'], loc, url, mode=mode)
                if local_market(stub) < 2:
                    continue
                page = Page(read_page(url))
                structured = [j for j in objects(page.blocks) if j.get('@type') == 'JobPosting']
                if not structured:
                    raise ValueError('Vacante sin detalle estructurado')
                item = structured_job(source, structured[0], url, normalize, valid_url)
                # Use applicant locations on the company job board, not HQ address.
                item.update(location=loc, mode=mode or item['mode'], eligibility=stub['eligibility'],
                    salary=row.get('salaryRange', ''), employment_type=row.get('type', ''),
                    apply_url=trusted(row['applyUrl'], ['account.ycombinator.com'], valid_url),
                    company_url=company.get('website') if valid_url(company.get('website', '')) else source['url'])
                add(item)
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                batch.rejected.append({'error': type(exc).__name__})
            sleep(0.1)
    elif provider == 'kushki_public':
        text = read_page(source['url'])
        chunks = []
        for match in re.finditer(r'self\.__next_f\.push\((\[.*?\])\)</script>', text):
            value = json.loads(match[1])
            if len(value) > 1 and isinstance(value[1], str):
                chunks.append(value[1])
        payload = ''.join(chunks)
        match = re.search(r'"jobs":(\[)', payload)
        if not match:
            raise ValueError('Kushki no devolvió un catálogo verificable')
        rows, _ = json.JSONDecoder().raw_decode(payload[match.start(1):])
        if not isinstance(rows, list):
            raise ValueError('Catálogo de Kushki inválido')
        for row in rows:
            # This list currently publishes SmartRecruiters-shaped summaries.
            url = trusted(row['postingUrl'], source['allowed_hosts'], valid_url)
            parse_detail(url)
    else:
        raise ValueError('Portal no implementado')
    if batch.rejected and not batch:
        raise ValueError('El portal devolvió anuncios que no pudieron verificarse')
    return batch
