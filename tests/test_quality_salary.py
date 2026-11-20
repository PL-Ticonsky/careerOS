import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import workspace
import salary_reference as fx
from career_rules import DEFAULT_PROFILE
from opportunity_quality import assess


class SalaryTest(unittest.TestCase):
    def setUp(self):
        self.rates = {'rates': {'USD': 1, 'COP': 4000, 'EUR': 0.8, 'INR': 80},
                      'time_last_update_unix': time.time(), 'time_last_update_utc': 'Fri, 20 Nov 2026 00:00:00 +0000'}

    def reference(self, text):
        return fx.reference({'salary': text, 'kind': 'empleo'}, self.rates)

    def test_conversion_preserves_period_and_original(self):
        self.assertEqual(self.reference('3000–6000 USD / monthly')['display'], '12.000.000–24.000.000 COP · por mes')
        self.assertEqual(self.reference('11.54–14.43 USD / hourly')['display'], '46.160–57.720 COP · por hora')
        self.assertEqual(self.reference('25–50 EUR · Precio fijo')['display'], '125.000–250.000 COP · Precio fijo')
        self.assertEqual(self.reference('1,500–2,500 USD / annual')['display'], '6.000.000–10.000.000 COP · por año')
        self.assertEqual(self.reference('1.500–2.500 COP / mes')['status'], 'native')
        self.assertEqual(self.reference('2.5k–3k USD / month')['display'], '10.000.000–12.000.000 COP · por mes')
        self.assertEqual(self.reference('Desde 100 USD / hour')['display'], 'Desde 400.000 COP · por hora')
        self.assertEqual(self.reference('?–100 USD / hour')['display'], '?–400.000 COP · por hora')
        lever = json.dumps({'min': 50000, 'max': 60000, 'currency': 'USD', 'interval': 'yearly'})
        self.assertEqual(self.reference(lever)['display'], '200.000.000–240.000.000 COP · por año')

    def test_ambiguous_and_stale_never_invent_conversion(self):
        for text in ('$3000–5000 / month', '100–200 · moneda y período por confirmar', 'USD 100 EUR 200', 'USD 100 plus 30 bonus', '100 USD / 2 weeks / 10 hours'):
            if text == '100 USD / 2 weeks / 10 hours':
                # An explicitly stated nonstandard period is preserved, not annualized.
                self.assertIn('2 weeks / 10 hours', self.reference(text)['display'])
            else:
                self.assertEqual(self.reference(text)['status'], 'unknown')
        self.rates['time_last_update_unix'] -= 8 * 86400
        self.assertEqual(self.reference('10 USD / hour')['status'], 'unavailable')
        self.assertEqual(self.reference('100 COP / hour')['status'], 'native')
        self.assertIsNone(fx.reference({'kind': 'evento', 'salary': '10 USD'}, self.rates))

    def test_daily_cache_avoids_network_and_failures_preserve_cache(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(fx, 'CACHE', Path(folder) / 'rates.json'), patch.object(fx, '_snapshot', None):
            fx.CACHE.write_text(json.dumps(dict(self.rates, fetched_at=time.time())))
            with patch.object(fx, 'urlopen') as request:
                fx.refresh()
                request.assert_not_called()
                self.assertEqual(fx.cached_rates()['rates']['COP'], 4000)
            with patch.object(fx, 'urlopen', side_effect=OSError('offline')):
                fx.CACHE.write_text(json.dumps(dict(self.rates, fetched_at=0)))
                fx.refresh()
                self.assertEqual(fx.cached_rates()['rates']['COP'], 4000)


class QualityTest(unittest.TestCase):
    def item(self, **kwargs):
        return dict(title='Python SQL', description='', kind='freelance', location='Remoto', mode='Remoto', **kwargs)

    def test_competition_zero_missing_and_verification(self):
        zero = assess(self.item(bid_count=0), DEFAULT_PROFILE)
        crowded = assess(self.item(bid_count=45), DEFAULT_PROFILE)
        missing = assess(self.item(), DEFAULT_PROFILE)
        self.assertTrue(zero['top'])
        self.assertGreater(zero['score'], crowded['score'])
        self.assertFalse(missing['top']); self.assertFalse(missing['low_competition'])
        for value in (None, -1, True, '3'):
            self.assertFalse(assess(self.item(bid_count=value), DEFAULT_PROFILE)['low_competition'])
        self.assertFalse(assess(self.item(bid_count=0, active=False), DEFAULT_PROFILE)['top'])
        self.assertFalse(assess(dict(self.item(bid_count=0), title='Unrelated'), DEFAULT_PROFILE)['top'])

    def test_profile_mismatch_prevents_top(self):
        item = dict(self.item(bid_count=0), level='Senior')
        self.assertFalse(assess(item, dict(DEFAULT_PROFILE, level='Junior'))['top'])
        job = dict(item, kind='empleo', location='Bogotá', level='Junior')
        self.assertTrue(assess(job, DEFAULT_PROFILE)['top'])
        self.assertFalse(assess(dict(job, location='US only'), DEFAULT_PROFILE)['top'])
        self.assertFalse(assess(dict(item, mode='Presencial', location='US only'), DEFAULT_PROFILE)['top'])

    def test_filters_sort_before_pagination_and_detail(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(app, 'DB', Path(folder) / 'db.sqlite'):
            app.init()
            items = []
            for i, bids in enumerate([70, None, 0, 8]):
                row = app.normalize('fixture', 'Python SQL', 'Client' + str(i), 'Remoto', 'https://example.com/' + str(i), kind='freelance', mode='Remoto')
                row.update(bid_count=bids, salary='10–20 USD · Por hora')
                items.append(row)
            app.store(items, 'fixture')
            query = lambda **kw: workspace.query(app.connect, {k: [v] for k,v in dict(view='freelance', **kw).items()})
            result = query(sort='relevance', limit='1')
            self.assertEqual(result['items'][0]['bid_count'], 0)
            self.assertEqual(query(priority='low_competition')['total'], 2)
            self.assertEqual(query(priority='top')['total'], 1)  # 8 bids -> 60 points, below 65
            self.assertEqual(workspace.detail(app.connect, items[2]['id'])['quality']['top'], True)
            with self.assertRaises(ValueError):
                query(priority='invented')
