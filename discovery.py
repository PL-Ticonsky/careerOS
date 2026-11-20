"""Bounded public-page discovery and on-demand Google Places prospecting."""
import json
import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from career_rules import fold


def eligible_event(item):
    """Physical attendance is local; hybrid elsewhere needs explicit online access."""
    if item.get('mode') == 'Remoto':
        restrictions = fold(item.get('location', '') + ' ' + item.get('description', '') + ' ' + item.get('requirements', ''))
        if re.search(r'(?:us|usa|uk|eu|india|canada|europe|united states)[ -]only|(?:solo|only) (?:para )?(?:residen\w*|citizens) (?:of |de |in )?(?:usa|india|canada|europa|united states)|(?:excluding|excepto|except) colombia', restrictions):
            return False
        return True
    return bool(re.search(r'\bbogota\b', fold(item.get('location', '') + ' ' + item.get('venue', '')))) and item.get('mode') in ('Presencial', 'Híbrido')


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.blocks = []; self.links = []; self.text = []; self.title = ''
        self.script = None; self.hidden = 0; self.in_title = False
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script':
            self.hidden += 1
            if attrs.get('type', '').lower() == 'application/ld+json': self.script = ''
        if tag == 'style': self.hidden += 1
        if tag == 'title' and not self.title: self.in_title = True
        if tag == 'body': self.in_title = False
        if tag == 'a' and attrs.get('href'): self.links.append(attrs['href'])
    def handle_data(self, text):
        if self.script is not None: self.script += text
        if not self.hidden: self.text.append(text)
        if self.in_title: self.title += text
    def handle_endtag(self, tag):
        if tag == 'script' and self.script is not None:
            try: self.blocks.append(json.loads(self.script))
            except ValueError: pass
            self.script = None
        if tag in ('script', 'style'): self.hidden = max(0, self.hidden - 1)
        if tag == 'title': self.in_title = False


def read_page(url):
    with urlopen(Request(url, headers={'User-Agent': 'CareerOS personal reader/1.0', 'Accept': 'text/html'}), timeout=20) as response:
        raw = response.read(3_000_001)
        if len(raw) > 3_000_000: raise ValueError('Página demasiado grande')
        return raw.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values(): yield from objects(child)
    elif isinstance(value, list):
        for child in value: yield from objects(child)


def calendar_day(value):
    try: return datetime.fromisoformat(str(value).replace('Z', '+00:00')).date().isoformat()
    except ValueError: return ''


def structured_event(source, row, normalize):
    types = row.get('@type', [])
    if isinstance(types, str): types = [types]
    if not any(t in ('Event', 'EducationEvent', 'BusinessEvent', 'Hackathon') for t in types): return None
    if any(s in str(row.get('eventStatus', '')) for s in ('EventCancelled', 'EventPostponed')): return None
    locations = row.get('location', [])
    if not isinstance(locations, list): locations = [locations]
    online = 'OnlineEventAttendanceMode' in str(row.get('eventAttendanceMode', ''))
    address = []
    for loc in locations:
        if isinstance(loc, str): address.append(loc); continue
        if not isinstance(loc, dict): continue
        online |= loc.get('@type') == 'VirtualLocation' and bool(loc.get('url'))
        addr = loc.get('address', '')
        address.append(' '.join(str(addr.get(k, '')) for k in ('streetAddress', 'addressLocality', 'addressRegion', 'addressCountry')) if isinstance(addr, dict) else str(addr))
        address.append(str(loc.get('name', '')))
    location = ' · '.join(p.strip() for p in address if p.strip())
    organizer = row.get('organizer', {})
    if isinstance(organizer, list): organizer = organizer[0] if organizer else {}
    company = organizer.get('name', '') if isinstance(organizer, dict) else str(organizer)
    start, end = calendar_day(row.get('startDate')), calendar_day(row.get('endDate'))
    if not start: raise ValueError('Evento sin fecha válida')
    item = normalize(source['id'], row.get('name'), company, ('Online' if online else location),
                     row.get('url'), str(row.get('description') or ''), mode='Remoto' if online else 'Presencial', kind='evento', event_date=start)
    item.update(event_end_date=end or start, venue=location, event_type='Meetup / evento',
                registration_url=item['url'], cost='Gratis' if row.get('isAccessibleForFree') is True else '',
                requirements='Confirma elegibilidad, cupos y horario en la inscripción.',
                verification='Evento publicado · inscripción por confirmar', description_scope='summary')
    offers = row.get('offers', {})
    if isinstance(offers, list): offers = offers[0] if offers else {}
    if isinstance(offers, dict) and offers.get('price') is not None:
        item['cost'] = 'Gratis' if str(offers['price']) == '0' else str(offers['price']) + ' ' + str(offers.get('priceCurrency', ''))
    return item if eligible_event(item) else None


def collect_web(source, normalize, batch_class, read=read_page):
    batch = batch_class(); seen = set()
    page = Page(read(source['url']))
    pages = [(source['url'], page)]
    # Follow only the configured publisher's bounded set of relevant pages.
    pattern = source.get('link_pattern')
    if pattern:
        links = list(dict.fromkeys(urljoin(source['url'], link).split('#')[0] for link in page.links))
        for link in [u for u in links if urlparse(u).hostname == urlparse(source['url']).hostname and re.search(pattern, u)][:source.get('max_pages', 8)]:
            if link == source['url']: continue
            try: pages.append((link, Page(read(link))))
            except (ValueError, OSError): batch.rejected.append({'error': 'Página no disponible'})
    for url, parsed in pages:
        for block in ([] if source.get('announcements') else parsed.blocks):
            for row in objects(block):
                try: item = structured_event(source, row, normalize)
                except (ValueError, TypeError, KeyError):
                    batch.rejected.append({'error': 'Evento incompleto'}); continue
                if item and item['id'] not in seen: seen.add(item['id']); batch.append(item)
        # Official training announcements are explicitly an inbox for verification,
        # never fabricated open registrations or free certification exams.
        if source.get('announcements'):
            body = re.sub(r'\s+', ' ', ' '.join(parsed.text)).strip()
            title = re.sub(r'\s+', ' ', parsed.title).strip()[:300]
            if source.get('listing_only') and url == source['url']: continue
            if not source.get('known_deadline') and not re.search(r'\b(?:aws|oracle|programaci\w*|ciberseg\w*|inteligencia artifi?cial|inteligencia artifical|cloud|tecnolog\w*|datos|sena|tic)\b', fold(title)): continue
            item = normalize(source['id'], title, source['name'], 'Por confirmar', url, body[:16000], kind='evento', mode='Por confirmar')
            articles = [o for b in parsed.blocks for o in objects(b) if o.get('@type') in ('Article', 'NewsArticle')]
            if articles:
                article = articles[0]
                item['published'] = str(article.get('datePublished') or '')
                item['description'] = str(article.get('articleBody') or article.get('description') or body[:16000])
            item['event_end_date'] = source.get('known_deadline', '')
            item['registration_deadline'] = source.get('known_deadline', '')
            item.update(event_type='Formación / certificaciones', verification='Por verificar: vigencia, modalidad, requisitos y beneficio',
                        discovery_only=True, description_scope='summary', registration_url=url,
                        summary='Anuncio oficial. No confirma inscripción abierta ni examen de certificación gratuito.')
            if item['id'] not in seen: seen.add(item['id']); batch.append(item)
    if not batch and not batch.rejected: raise ValueError('No se encontraron convocatorias legibles; la página puede haber cambiado o no tener eventos')
    return batch


def places_search(data, opener=urlopen, key=None):
    query, area = data.get('query', ''), data.get('area', '')
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 100: raise ValueError('Escribe un tipo de negocio (2–100 caracteres)')
    if not isinstance(area, str) or len(area) > 100: raise ValueError('Barrio inválido')
    key = os.environ.get('GOOGLE_PLACES_API_KEY', '') if key is None else key
    if not key: raise ValueError('Configura GOOGLE_PLACES_API_KEY en el servidor y habilita Places API (New) con facturación en Google Cloud. La búsqueda puede tener costo.')
    payload = {'textQuery': f'{query.strip()} {area.strip()} Bogotá Colombia', 'languageCode': 'es', 'regionCode': 'CO', 'pageSize': 20,
               'locationRestriction': {'rectangle': {'low': {'latitude': 4.45, 'longitude': -74.23}, 'high': {'latitude': 4.85, 'longitude': -73.99}}}}
    if data.get('page_token'):
        if not isinstance(data['page_token'], str) or len(data['page_token']) > 4096: raise ValueError('Página inválida')
        payload['pageToken'] = data['page_token']
    mask = 'nextPageToken,places.attributions,places.id,places.displayName,places.formattedAddress,places.addressComponents,places.websiteUri,places.googleMapsUri,places.nationalPhoneNumber,places.businessStatus,nextPageToken'
    request = Request('https://places.googleapis.com/v1/places:searchText', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'X-Goog-Api-Key': key, 'X-Goog-FieldMask': mask})
    try:
        with opener(request, timeout=25) as response: result = json.load(response)
    except HTTPError as exc:
        raise ValueError(f'Google Places devolvió HTTP {exc.code}. Revisa la clave, los permisos, la facturación y la cuota.') from None
    except (URLError, TimeoutError): raise ValueError('Google Places no respondió. Intenta de nuevo.') from None
    if not isinstance(result, dict) or not isinstance(result.get('places', []), list):
        raise ValueError('Google Places devolvió una respuesta inesperada.')
    leads = []
    for row in result.get('places', []):
        locality = ' '.join(c.get('longText', '') for c in row.get('addressComponents', []) if 'locality' in c.get('types', []))
        if not re.search(r'\bbogota\b', fold(locality)): continue
        if row.get('websiteUri') or row.get('businessStatus') == 'CLOSED_PERMANENTLY': continue
        leads.append({'place_id': row['id'], 'name': row.get('displayName', {}).get('text', ''), 'address': row.get('formattedAddress', ''),
                      'phone': row.get('nationalPhoneNumber', ''), 'url': row.get('googleMapsUri', ''), 'attributions': row.get('attributions') or [],
                      'signal': 'Sin sitio web publicado en la ficha; verifica si tiene web por otro medio.'})
    return {'items': leads, 'next_page_token': result.get('nextPageToken', ''), 'examined': len(result.get('places', [])), 'attribution': 'Google Maps'}
