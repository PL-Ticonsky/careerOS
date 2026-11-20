import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

import app
import workspace
import application_analytics as analytics


class AnalyticsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(app, 'DB', Path(self.temp.name) / 'personal.db')
        self.patch.start(); app.init()

    def tearDown(self):
        self.patch.stop(); self.temp.cleanup()

    def item(self, suffix, kind='empleo'):
        row = app.normalize('fixture', 'Python ' + suffix, 'Example', 'Colombia', 'https://example.com/' + suffix, kind=kind)
        app.store([row], 'fixture', False)
        return row['id']

    def status(self, item, **changes):
        workspace.update_tracking(app.connect, dict(id=item, **changes))

    def report(self, params=''):
        return analytics.report(app.connect, parse_qs(params))

    def test_empty_saved_and_events_are_not_applications(self):
        self.status(self.item('saved'), status='Guardada', favorite=True)
        self.status(self.item('event', 'evento'), status='Postulada')
        report = self.report()
        self.assertEqual(report['total'], 0)
        self.assertEqual(len(report['monthly']), 6)
        self.assertTrue(all(month['count'] == 0 for month in report['monthly']))

    def test_automatic_date_and_advance_preserve_first_application(self):
        item = self.item('applied')
        with patch.object(workspace, 'today', return_value='2026-11-01'):
            self.status(item, status='Postulada', applied_via='LinkedIn')
        self.status(item, status='Entrevista', next_action='Preparar entrevista', due_date='2020-01-01')
        report = self.report(); row=report['items'][0]
        self.assertEqual(row['applied_date'], '2026-11-01')
        self.assertEqual(row['applied_via'], 'LinkedIn')
        self.assertEqual(row['status'], 'Entrevista')
        self.assertEqual(report['summary']['active'], 1)
        self.assertEqual(report['summary']['interviews'], 1)
        self.assertEqual(report['summary']['due'], 1)
        self.assertEqual(len(workspace.detail(app.connect,item)['timeline']), 2)
        self.status(item, status='Descartada')
        self.assertEqual(self.report()['total'], 1)
        self.assertEqual(self.report()['summary']['active'], 0)
        self.assertEqual(self.report()['summary']['due'], 0)

    def test_advanced_without_application_does_not_invent_date(self):
        item = self.item('unknown');self.status(item,status='Entrevista')
        self.assertEqual(self.report()['summary']['unknown_date'],1)
        self.assertEqual(self.report()['items'][0]['applied_date'],'')
        self.assertEqual(self.report('period=30')['total'],0)

    def test_filters_totals_pagination_and_manual_date(self):
        for i in range(4):
            item=self.item(str(i),'freelance' if i%2 else 'empleo')
            self.status(item,status='Postulada',applied_date=f'2026-01-0{i+1}')
        self.assertEqual(self.report('kind=freelance')['total'],2)
        self.assertEqual(self.report('query=Python+1')['total'],1)
        first=self.report('limit=2');second=self.report('limit=2&offset=2')
        self.assertEqual(first['summary']['total'],4)
        self.assertEqual(first['items'][0]['applied_date'],'2026-01-04')
        self.assertTrue(first['has_more']);self.assertFalse(second['has_more'])
        self.assertFalse({i['id'] for i in first['items']} & {i['id'] for i in second['items']})
        for params in ['period=3','kind=evento','stage=Inventada','limit=101','offset=-1','limit=no']:
            with self.subTest(params=params),self.assertRaises(ValueError):self.report(params)

    def test_invalid_dates_and_backup_compatibility(self):
        item=self.item('backup')
        for value in ['2026-02-30','invalid','2999-01-01']:
            with self.assertRaises(ValueError):self.status(item,applied_date=value)
        self.status(item,status='Postulada',applied_date='2026-01-02',applied_via='Correo')
        backup=workspace.backup(app.connect)
        self.status(item,applied_date='2026-01-03',applied_via='Otro')
        workspace.restore(app.connect, app.DB, backup, app.valid_url)
        detail=workspace.detail(app.connect,item)
        self.assertEqual((detail['applied_date'],detail['applied_via']),('2026-01-02','Correo'))
        for row in backup['opportunities']:
            row.pop('applied_date');row.pop('applied_via')
        workspace.restore(app.connect, app.DB, backup, app.valid_url)
        self.assertEqual(self.report()['total'],1)
        self.assertEqual(self.report()['items'][0]['date_source'],'history')

    def test_utc_history_date_is_converted_to_bogota(self):
        self.assertEqual(analytics.local_date('2026-11-20T02:00:00+00:00'),'2026-11-19')
        self.assertEqual(analytics.local_date('invalid'),'')
