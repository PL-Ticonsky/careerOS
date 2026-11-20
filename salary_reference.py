"""Conservative COP estimates with a daily cached, keyless public FX service."""
import json
import math
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

CACHE = Path(__file__).resolve().parent / 'data/exchange-rates.json'
_lock = threading.Lock()
_snapshot = None


def refresh():
    global _snapshot
    try:
        if CACHE.exists():
            cached = json.loads(CACHE.read_text())
            if time.time() - cached.get('fetched_at', 0) < 86400:
                _snapshot = cached
                return
        with urlopen(Request('https://open.er-api.com/v6/latest/USD', headers={'User-Agent': 'CareerOS/1.0'}), timeout=12) as response:
            data = json.loads(response.read(100000))
        if data.get('result') != 'success' or data.get('base_code') != 'USD' or not data.get('rates', {}).get('COP'):
            return
        data['fetched_at'] = time.time()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        temporary = CACHE.with_suffix('.tmp')
        temporary.write_text(json.dumps(data))
        temporary.replace(CACHE)
        with _lock:
            _snapshot = data
    except (OSError, ValueError, TypeError):
        pass  # An unavailable rate must never prevent browsing opportunities.


def start(cache):
    global CACHE
    CACHE = Path(cache)
    def worker():
        while True:
            refresh()
            threading.Event().wait(3600)
    threading.Thread(target=worker, daemon=True, name='salary-rates').start()


def cached_rates():
    global _snapshot
    with _lock:
        if _snapshot is None:
            try:
                _snapshot = json.loads(CACHE.read_text())
            except (OSError, ValueError):
                return {}
        return _snapshot


def numeric(text):
    text = text.strip().lower()
    multiplier = 1000 if text.endswith('k') else 1
    text = text.removesuffix('k').replace(' ', '')
    # One grouping convention per token; ambiguous single 3-digit suffix is
    # interpreted as grouping (salary inputs never require mill precision).
    if ',' in text and '.' in text:
        decimal = ',' if text.rfind(',') > text.rfind('.') else '.'
        text = text.replace('.' if decimal == ',' else ',', '').replace(decimal, '.')
    elif re.fullmatch(r'\d{1,3}([.,]\d{3})+', text):
        text = text.replace(',', '').replace('.', '')
    else:
        text = text.replace(',', '.')
    value = float(text) * multiplier
    if not math.isfinite(value) or value <= 0:
        raise ValueError('Invalid amount')
    return value


def parse_salary(value):
    text = str(value or '').strip()
    if not text or 'por confirmar' in text.lower():
        return None
    if text.startswith('{'):
        try:
            data = json.loads(text)
            currency = data['currency'].upper()
            values = [float(data[k]) for k in ('min', 'max') if data.get(k) is not None]
            if not values or any(not math.isfinite(v) or v <= 0 for v in values):
                return None
            return currency, values, str(data.get('interval') or 'período no publicado')
        except (ValueError, TypeError, KeyError, AttributeError):
            return None
    # Never infer a currency from the ambiguous "$" symbol or job location.
    currencies = re.findall(r'\b(?:USD|COP|EUR|GBP|CAD|AUD|INR|BRL|MXN|CLP|ARS|PEN|CHF|NZD|SGD|HKD|JPY|CNY|ZAR|PHP|PKR|BDT|SEK|NOK|DKK|PLN|AED|CZK|HUF|RON|TRY|UAH|IDR|MYR|THB|KRW|VND|EGP|NGN|KES)\b', text.upper())
    if len(set(currencies)) != 1:
        return None
    currency = currencies[0]
    amount, separator, period = re.split(r'(/|·|\bper\b)', text, maxsplit=1, flags=re.I) if re.search(r'/|·|\bper\b', text, re.I) else (text, '', '')
    amount = re.sub(r'\b' + currency + r'\b|US\$|[$€£]', '', amount, flags=re.I).strip()
    # Accept simple numeric ranges and explicit open bounds; reject prose,
    # additional unrelated numbers, or mixed salary periods.
    amount = re.sub(r'^(?:from|desde|up to|hasta)\s+', '', amount, flags=re.I)
    if not re.fullmatch(r'[\d\s.,kK?]+(?:\s*[–—-]\s*[\d\s.,kK?]+)?', amount):
        return None
    try:
        values = [numeric(v) for v in re.split('[–—-]', amount) if v.strip() != '?']
        if not values or len(values) > 2 or (len(values) == 2 and values[0] > values[1]):
            return None
        # Preserve missing/open bounds instead of turning them into a fixed pay.
        tokens = [v.strip() for v in re.split('[–—-]', amount)]
        return currency, [None if v == '?' else numeric(v) for v in tokens], period.strip() or 'período no publicado'
    except ValueError:
        return None


def reference(item, rates=None):
    if item.get('kind') == 'evento':
        return None
    original = str(item.get('salary') or '')
    parsed = parse_salary(original)
    if not parsed:
        return {'status': 'unknown', 'note': 'Moneda o importe sin confirmar; se conserva el dato original.'} if original else None
    currency, values, period = parsed
    labels = {'hourly': 'por hora', 'hour': 'por hora', 'monthly': 'por mes', 'month': 'por mes',
              'annual': 'por año', 'yearly': 'por año', 'year': 'por año', 'week': 'por semana', 'weekly': 'por semana'}
    period = labels.get(period.lower(), period)
    data = rates if rates is not None else cached_rates()
    if currency == 'COP':
        factor = 1
    else:
        try:
            # A week-old rate is no longer useful for today's salary estimate.
            if time.time() - data['time_last_update_unix'] > 7 * 86400:
                raise ValueError('stale')
            factor = data['rates']['COP'] / data['rates'][currency]
            if not math.isfinite(factor) or factor <= 0:
                raise ValueError('invalid')
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return {'status': 'unavailable', 'note': 'Conversión a COP no disponible; consulta el importe original.'}
    converted = [round(v * factor) if v is not None else None for v in values]
    formatted = [('?' if v is None else f'{v:,}'.replace(',', '.')) for v in converted]
    prefix = 'Hasta ' if re.match(r'^(up to|hasta)\b', original, re.I) else 'Desde ' if re.match(r'^(from|desde)\b', original, re.I) else ''
    return {'status': 'native' if currency == 'COP' else 'converted',
            'display': prefix + '–'.join(formatted) + ' COP · ' + period,
            'estimated': currency != 'COP', 'currency': currency,
            'updated': datetime.fromtimestamp(data['time_last_update_unix'], timezone.utc).date().isoformat() if currency != 'COP' else '',
            'provider_url': 'https://www.exchangerate-api.com' if currency != 'COP' else ''}
