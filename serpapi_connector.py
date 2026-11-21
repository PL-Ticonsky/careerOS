"""Google Jobs discovery through SerpApi, with bounded searches and private keys."""
import json
import call_center
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


def key(db=None):
    environment = os.environ.get('SERPAPI_API_KEY', '').strip()
    if environment or db is None:
        return environment
    try:
        value = json.loads((Path(db).parent / 'serpapi-private.json').read_text()).get('key', '')
    except (OSError, ValueError, AttributeError):
        return ''
    return value.strip() if isinstance(value, str) else ''


def request(params, credential, account=False):
    if not isinstance(credential, str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', credential):
        raise ValueError('Falta una clave válida de SerpApi en la configuración local.')
    url = 'https://serpapi.com/' + ('account.json' if account else 'search.json')
    url += '?' + urlencode(dict(params, api_key=credential))
    try:
        with urlopen(Request(url, headers={'User-Agent': 'CareerOS personal reader/1.0', 'Accept': 'application/json'}), timeout=35) as response:
            data = json.load(response)
    except HTTPError as exc:
        raise ValueError(f'SerpApi devolvió HTTP {exc.code}. Revisa la clave y la cuota de tu cuenta.') from None
    except (URLError, TimeoutError, OSError):
        raise ValueError('SerpApi no respondió. Se conservan las ofertas anteriores.') from None
    except ValueError:
        raise ValueError('SerpApi devolvió una respuesta no válida.') from None
    if not isinstance(data, dict):
        raise ValueError('SerpApi devolvió un formato inesperado.')
    if data.get('error'):
        message = str(data['error']).lower()
        if not account and ("hasn't returned any results" in message or 'no results' in message):
            return {'jobs_results': []}
        raise ValueError('SerpApi rechazó la consulta. Revisa la clave, la cuota y el estado del proveedor.')
    return data


def account(credential):
    data = request({}, credential, account=True)
    # Never expose the account API's key, email, account ID or arbitrary fields.
    return {name: data[name] for name in ('searches_per_month', 'total_searches_left', 'this_month_usage')
            if type(data.get(name)) is int and data[name] >= 0}


def listing_link(value, valid_url):
    if not isinstance(value, str) or not valid_url(value):
        return ''
    parsed = urlparse(value)
    if parsed.hostname == 'serpapi.com' or parsed.hostname.endswith('.serpapi.com'):
        return ''
    params = parse_qsl(parsed.query, keep_blank_values=True)
    if any(name.lower() in ('api_key', 'apikey', 'access_token') for name, _ in params):
        return ''
    params = [(name, val) for name, val in params if not name.lower().startswith('utm_')
              and not (name == 'source' and val == 'google_jobs_apply')]
    return urlunparse(parsed._replace(query=urlencode(params)))


def record(source, row, normalize, valid_url):
    options = []
    for option in row.get('apply_options') or []:
        if not isinstance(option, dict): continue
        link = listing_link(option.get('link'), valid_url)
        if link and link not in {o['link'] for o in options}:
            options.append({'title': str(option.get('title') or 'Consultar oferta')[:200], 'link': link})
    url = options[0]['link'] if options else listing_link(row.get('source_link') or row.get('share_link'), valid_url)
    if not url:
        raise ValueError('La oferta no tiene un enlace público válido')
    detected = row.get('detected_extensions') or {}
    salary = detected.get('salary') or next((v for v in (row.get('extensions') or [])
        if isinstance(v, str) and re.search(r'(?:[$€£]|\bCOP\b|\bUSD\b|\bEUR\b)', v)), '')
    item = normalize(source['id'], row['title'], row.get('company_name', ''), row.get('location', ''), url,
                     row.get('description', ''), salary=salary,
                     mode='Remoto' if detected.get('work_from_home') is True else 'Por confirmar')
    item.update(apply_options=options, listing_provider=str(row.get('via') or ''),
                provider_id=str(row.get('job_id') or ''), description_scope='full',
                published_label=str(detected.get('posted_at') or ''))
    return item


def collect(source, credential, normalize, valid_url, batch_class, local_market, sleep):
    queries, pages = source.get('queries'), source.get('max_pages', 1)
    if not isinstance(queries, list) or not 1 <= len(queries) <= 5 or not all(isinstance(q, str) and 1 <= len(q) <= 150 for q in queries):
        raise ValueError('Configura entre una y cinco búsquedas de SerpApi.')
    if type(pages) is not int or not 1 <= pages <= 2:
        raise ValueError('SerpApi admite una o dos páginas por búsqueda en CareerOS.')
    quota = account(credential)
    if quota.get('total_searches_left', 0) < len(queries) * pages:
        raise ValueError('No queda cuota suficiente en SerpApi para completar estas búsquedas. Se conservan las ofertas anteriores.')
    batch, by_id = batch_class(), {}
    batch.search_results = []
    batch.quota_before = quota
    for query in queries:
        token, tokens = '', set()
        found, accepted = 0, 0
        for page in range(pages):
            params = {'engine': 'google_jobs', 'q': query, 'location': 'Bogota, Colombia', 'gl': 'co', 'hl': 'es'}
            if token: params['next_page_token'] = token
            data = request(params, credential)
            rows = data.get('jobs_results')
            if not isinstance(rows, list):
                raise ValueError('SerpApi no devolvió una lista de ofertas.')
            found += len(rows)
            for index, row in enumerate(rows):
                try:
                    item = record(source, row, normalize, valid_url)
                    # Search origin is not proof that a remote role accepts Colombia.
                    if source['id'] == call_center.SOURCE:
                        item['mode'] = call_center.mode(item)
                        if not call_center.matches(item, local_market(item)):
                            continue
                    elif local_market(item) < 2:
                        continue
                    accepted += 1
                    if item['id'] in by_id:
                        previous = by_id[item['id']]
                        if query not in previous['discovery_queries']: previous['discovery_queries'].append(query)
                        for option in item['apply_options']:
                            if option not in previous['apply_options']: previous['apply_options'].append(option)
                    else:
                        item['discovery_queries'] = [query]
                        by_id[item['id']] = item; batch.append(item)
                except (ValueError, KeyError, TypeError, AttributeError, OverflowError, OSError):
                    batch.rejected.append({'record': index, 'error': 'Oferta de Google Jobs incompleta'})
            token = (data.get('serpapi_pagination') or {}).get('next_page_token', '')
            if not token: break
            if not isinstance(token, str) or len(token) > 10000 or token in tokens:
                raise ValueError('SerpApi devolvió una paginación inválida.')
            tokens.add(token)
            if page + 1 < pages: sleep(0.3)
        batch.search_results.append({'query': query, 'returned': found, 'compatible': accepted})
        sleep(0.3)
    if batch.rejected and not batch:
        raise ValueError('Todas las ofertas recibidas de SerpApi estaban incompletas.')
    return batch
