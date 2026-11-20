"""Read the event data published in MLH's public season calendar."""
import json
from html.parser import HTMLParser
from urllib.parse import urljoin

from discovery import calendar_day, eligible_event, read_page


class CalendarPage(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.reading = False
        self.content = ''
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('type') == 'application/json' and attrs.get('data-page') == 'app':
            self.reading = True

    def handle_data(self, data):
        if self.reading: self.content += data

    def handle_endtag(self, tag):
        if tag == 'script': self.reading = False


def collect_mlh(source, normalize, valid_url, batch_class, read=read_page):
    from job_connectors import public_url
    url = public_url(source['url'], valid_url, 'mlh.com')
    page = CalendarPage(read(url))
    try:
        rows = json.loads(page.content)['props']['upcomingEvents']
    except (ValueError, KeyError, TypeError):
        raise ValueError('El calendario público de MLH no tiene el formato esperado') from None
    if not isinstance(rows, list):
        raise ValueError('MLH no devolvió una lista de eventos')
    batch, seen = batch_class(), set()
    for row in rows:
        try:
            format_type = row.get('formatType')
            mode = 'Remoto' if format_type in ('virtual', 'online', 'digital') else 'Presencial' if format_type == 'physical' else 'Híbrido' if format_type == 'hybrid' else 'Por confirmar'
            venue = row.get('venueAddress') or {}
            location = ', '.join(dict.fromkeys(str(x) for x in (row.get('location'), venue.get('city'), venue.get('state'), venue.get('country')) if x))
            start, end = calendar_day(row.get('startsAt')), calendar_day(row.get('endsAt'))
            if not start or not end:
                raise ValueError('Evento sin fechas válidas')
            item = normalize(source['id'], row['name'], row.get('organizationName') or 'Major League Hacking',
                'Online' if mode == 'Remoto' else location,
                public_url(urljoin(url, row['url']), valid_url, 'mlh.com'),
                description='Evento publicado en el calendario de Major League Hacking. Consulta requisitos, inscripción y horarios en la convocatoria original.',
                mode=mode, kind='evento', event_date=start)
            registration = row.get('websiteUrl')
            item.update(event_end_date=end, venue=location, event_type='Hackatón',
                registration_url=registration if valid_url(registration) else item['url'],
                description_scope='summary', cost='',
                verification='Calendario público de MLH · requisitos e inscripción por confirmar',
                topics=(row.get('customFields') or {}).get('hackathon_focus') or [])
            if eligible_event(item) and item['id'] not in seen:
                seen.add(item['id']); batch.append(item)
        except (ValueError, KeyError, TypeError, AttributeError):
            batch.rejected.append({'error': 'Evento de MLH incompleto'})
    if batch.rejected and not batch:
        # Distinguish an incompatible but valid calendar (successful zero results)
        # from broken records, which must not deactivate previous observations.
        raise ValueError('El calendario de MLH contiene eventos incompletos')
    return batch
