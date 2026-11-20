import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

import app
import opportunity_sources as adapters
import workspace
from test_app import CareerOSTest as BaseTests


class OpportunitySourcesTest(unittest.TestCase):
    setUp = BaseTests.setUp
    tearDown = BaseTests.tearDown

    def project(self, **changes):
        row = dict(id=123, status='active', frontend_project_status='open', title='Build a Python API',
                   seo_url='python/build-python-api', description='Need a FastAPI service. Deliver source and tests.',
                   jobs=[{'name': 'Python'}, {'name': 'FastAPI'}], currency={'code': 'USD'},
                   budget={'minimum': 100, 'maximum': 500}, type='fixed', submitdate=1795030000,
                   local=False, owner_info={'country': {'name': 'United Kingdom'}, 'city': 'London',
                                           'status': {'payment_verified': True}}, bid_stats={'bid_count': 4})
        row.update(changes); return row

    def event(self, **changes):
        row = dict(id=23, title='Synthetic Hackathon', open_state='open', invite_only=False,
                   url='https://synthetic.devpost.com/', displayed_location={'location': 'Online'},
                   submission_period_dates='Nov 12 - Dec 04, 2026', organization_name='Synthetic Organizer',
                   themes=[{'name': 'Web'}, {'name': 'Machine Learning/AI'}],
                   prize_amount='$<span>10,000</span>', registrations_count=42,
                   start_a_submission_url='https://synthetic.devpost.com/challenges/start_a_submission')
        row.update(changes); return row

    def parse_project(self, row):
        return adapters.freelancer_record({'id': 'freelancer'}, row, app.normalize, app.valid_url)

    def parse_event(self, row):
        return adapters.devpost_record({'id': 'devpost'}, row, app.normalize, app.valid_url, app.plain)

    def test_project_preserves_need_budget_and_public_contact_limits(self):
        item = self.parse_project(self.project())
        self.assertEqual(item['kind'], 'freelance')
        self.assertIn('Deliver source and tests', item['description'])
        self.assertEqual(item['salary'], '100–500 USD · Precio fijo')
        self.assertEqual(item['required_skills'], ['Python', 'FastAPI'])
        self.assertEqual(item['client_location'], 'London, United Kingdom')
        self.assertEqual(item['eligibility'], 'Por confirmar')
        self.assertEqual(item['company'], ''); self.assertEqual(item['contact_email'], '')
        self.assertEqual(item['contact_url'], item['url']); self.assertTrue(item['payment_verified'])

    def test_named_owner_and_hourly_budget(self):
        item = self.parse_project(self.project(type='hourly', budget={'minimum': 0, 'maximum': 30},
                                              _owner={'display_name': 'Public Client', 'username': 'publicclient'}))
        self.assertEqual(item['contact_name'], 'Public Client')
        self.assertEqual(item['contact_url'], 'https://www.freelancer.com/u/publicclient')
        self.assertEqual(item['salary'], '0–30 USD · Por hora')

    def test_nonpublic_closed_and_invite_only_records_are_skipped(self):
        for change in [dict(nonpublic=True), dict(deleted=True), dict(frontend_project_status='closed'), dict(status='closed')]:
            self.assertIsNone(self.parse_project(self.project(**change)))
        self.assertIsNone(self.parse_event(self.event(invite_only=True)))
        self.assertIsNone(self.parse_event(self.event(open_state='closed')))

    def test_event_preserves_dates_prize_and_does_not_invent_fee(self):
        item = self.parse_event(self.event())
        self.assertEqual(item['kind'], 'evento'); self.assertEqual(item['company'], 'Synthetic Organizer')
        self.assertEqual((item['event_date'], item['event_end_date']), ('2026-11-12', '2026-12-04'))
        self.assertEqual(item['submission_deadline'], '2026-12-04'); self.assertEqual(item['registration_deadline'], '')
        self.assertEqual(item['prizes'], '$10,000')
        self.assertEqual(item['cost'], ''); self.assertEqual(item['salary'], '')
        self.assertEqual(item['contact_email'], '')
        self.assertEqual(item['description_scope'], 'summary')
        self.assertEqual(item['eligibility'], 'Por confirmar')
        self.assertIn('Temáticas: Web, Machine Learning/AI', item['description'])

    def test_event_range_handles_cross_year_and_missing_year(self):
        self.assertEqual(adapters.event_dates('Dec 30 - Jan 15, 2027'), ('2026-12-30', '2027-01-15'))
        self.assertEqual(adapters.event_dates('Jul 16, 2026 - Jan 15, 2027'), ('2026-07-16', '2027-01-15'))
        self.assertEqual(adapters.event_dates('Nov 11 - 30, 2026'), ('2026-11-11', '2026-11-30'))
        for period in ['Nov 11 - 30', 'Feb 30, 2027', 'Later']:
            self.assertEqual(adapters.event_dates(period), ('', ''))

    def test_virtual_and_hybrid_event_locations(self):
        for location, mode in [('virtual','Remoto'), ('Online','Remoto'), ('Hybrid','Híbrido'),
                               ('Online and in-person','Híbrido'), ('Bogotá, Colombia','Presencial')]:
            with self.subTest(location=location):
                self.assertEqual(self.parse_event(self.event(displayed_location={'location':location}))['mode'],mode)

    def test_unsafe_provider_urls_rejected(self):
        for url in ['javascript:alert(1)', 'https://devpost.com.evil.example/event', 'http://127.0.0.1/test']:
            with self.assertRaises(ValueError): self.parse_event(self.event(url=url))
        for slug in ['//evil.example', 'python/../../evil', 'https://evil.example']:
            with self.assertRaises(ValueError): self.parse_project(self.project(seo_url=slug))

    def test_provider_pagination_deduplication_and_partial_rows(self):
        first = {'hackathons': [self.event(), {}], 'meta': {'per_page': 2, 'total_count': 3}}
        second = {'hackathons': [self.event()], 'meta': {'per_page': 2, 'total_count': 3}}
        with patch.object(app, 'fetch', side_effect=[first, second]) as fetch, patch.object(app.time, 'sleep'):
            batch = app.collect({'id': 'devpost', 'provider': 'devpost', 'max_pages': 2})
        self.assertEqual(len(batch), 1); self.assertEqual(len(batch.rejected), 1)
        self.assertIn('page=2', fetch.call_args_list[1].args[0])
        raw = {'status': 'success', 'result': {'projects': [self.project()], 'users': {}}}
        with patch.object(app, 'fetch', return_value=raw) as fetch:
            batch = app.collect({'id': 'freelancer', 'provider': 'freelancer', 'queries': ['python', 'backend']})
        self.assertEqual(len(batch), 1); self.assertEqual(fetch.call_count, 2)
        self.assertIn('full_description=true', fetch.call_args_list[0].args[0])

    def test_upstream_failure_preserves_previous_source_data(self):
        item = self.parse_event(self.event()); app.store([item], 'devpost')
        raw = {'hackathons': [self.event(title='Changed')], 'meta': {'per_page': 1, 'total_count': 2}}
        with patch.object(app, 'sources', return_value=[{'id': 'devpost', 'provider': 'devpost', 'enabled': True}]), patch.object(app, 'fetch', side_effect=[raw, ValueError('network')]), patch.object(app.time, 'sleep'):
            result = app.sync()
        self.assertIn('error', result['results'][0])
        self.assertEqual(workspace.detail(app.connect, item['id'])['title'], 'Synthetic Hackathon')

    def test_manual_contact_and_event_details_roundtrip_backup(self):
        item = app.manual_record(dict(kind='evento', mode='Presencial', title='Synthetic workshop',
            company='Organizer', url='https://example.com/workshop', salary='Gratis',
            event_date='2027-01-10', event_end_date='2027-01-11', registration_deadline='2027-01-09',
            contact_name='Public Organizer', contact_email='events@example.com', contact_phone='+57 300 000 0000',
            contact_url='https://example.com/contact', requirements='Bring a laptop',
            deliverables='Present a project', venue='Bogotá', prizes='Certificate'))
        app.store([item], 'manual', False)
        backup = workspace.backup(app.connect)
        workspace.validate_backup(backup, app.valid_url)
        saved = workspace.detail(app.connect, item['id'])
        self.assertEqual(saved['cost'], 'Gratis'); self.assertEqual(saved['salary'], '')
        self.assertEqual(saved['contact_email'], 'events@example.com')
        self.assertEqual(saved['requirements'], 'Bring a laptop')
        page = workspace.query(app.connect, parse_qs('view=evento&salary=1&sort=event'))
        self.assertEqual(page['total'], 1); self.assertIn('summary', page['items'][0])

    def test_manual_contact_validation(self):
        base = dict(kind='freelance', mode='Remoto', title='Project', url='https://example.com/project')
        for change in [dict(contact_email='bad\n@example.com'), dict(contact_url='javascript:alert(1)'),
                       dict(project_deadline='2027-02-30'), dict(event_date='2027-01-10', event_end_date='2027-01-09')]:
            with self.assertRaises(ValueError): app.manual_record(dict(base, **change))

    def test_events_expire_and_metrics_are_by_kind(self):
        past = self.parse_event(self.event(submission_period_dates='Jan 01 - 02, 2000'))
        app.store([past], 'devpost'); app.store([self.parse_project(self.project())], 'freelancer')
        self.assertEqual(workspace.query(app.connect, parse_qs('view=evento'))['total'], 0)
        self.assertEqual(workspace.query(app.connect, parse_qs('view=evento&inactive=1'))['items'][0]['availability'], 'Vencida')
        stats = workspace.metadata(app.connect, [], [])['stats']['by_kind']
        self.assertEqual(stats['freelance']['active'], 1); self.assertEqual(stats['evento']['active'], 0)


del BaseTests
