import tempfile
import unittest
from pathlib import Path

import app
import tech_radar
import workspace


class TechRadarTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = app.DB
        app.DB = Path(self.temp.name) / 'radar.db'
        app.init()

    def tearDown(self):
        app.DB = self.old_db
        self.temp.cleanup()

    def job(self, company, suffix, **fields):
        item = app.normalize('test', 'Python Developer ' + suffix, company,
                             'Bogotá, Colombia', 'https://example.com/' + suffix, 'Python SQL')
        item.update(fields)
        app.store([item], 'test', False)
        return item

    def query(self, **params):
        return workspace.query(app.connect, {'view': ['empleo'], 'startups': ['1'], **{k: [v] for k, v in params.items()}})

    def test_matches_employer_aliases_only_and_excludes_other_kinds(self):
        for index, company in enumerate(['EPAM Systems', 'Sofka Technologies', 'Softka', 'Cobre']):
            self.job(company, str(index))
        self.job('Other company', 'other', description='We work with EPAM and Sofka')
        self.job('Not EPAM', 'unrelated')
        self.job('EPAM', 'event', kind='evento')
        self.assertEqual(self.query()['total'], 4)
        self.assertEqual(self.query(tech_company='sofka')['total'], 2)
        self.assertEqual(tech_radar.company_id('  EPAM SYSTEMS, Inc. '), 'epam')
        with self.assertRaises(ValueError):
            self.query(tech_company='unknown')

    def test_market_availability_tracking_and_pagination(self):
        local = self.job('EPAM Systems', 'local')
        self.job('EPAM', 'germany', location='Germany')
        self.job('EPAM', 'expired', expires=1)
        self.assertEqual(self.query(market='colombia')['total'], 1)
        self.assertEqual(self.query(inactive='1')['total'], 3)
        page = self.query(limit='1')
        self.assertEqual(len(page['items']), 1)
        self.assertTrue(page['has_more'])
        workspace.update_tracking(app.connect, {'id': local['id'], 'favorite': True, 'notes': 'Keep me'})
        self.assertEqual(self.query(market='colombia')['total'], 0)
        saved = self.query(market='colombia', show_saved='1')['items'][0]
        self.assertEqual(saved['kind'], 'empleo')
        self.assertEqual(workspace.detail(app.connect, saved['id'])['notes'], 'Keep me')
        tracking = workspace.query(app.connect, {'view': ['tracking']})
        self.assertEqual(tracking['items'][0]['id'], local['id'])

    def test_company_filter_does_not_leak_into_other_views(self):
        self.job('EPAM', 'a')
        self.job('Other company', 'b')
        result = workspace.query(app.connect, {'view': ['empleo'], 'tech_company': ['epam']})
        self.assertEqual(result['total'], 2)
        self.assertIn('blend', {c['id'] for c in workspace.metadata(app.connect, [], [])['tech_companies']})
        self.assertEqual(workspace.metadata(app.connect, [], [])['stats']['by_kind']['startups']['total'], 1)
