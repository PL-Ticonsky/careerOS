import copy
import json
import os
import time
import unittest
from unittest.mock import patch
from urllib.error import URLError

import app
import job_connectors
import workspace
from test_app import CareerOSTest as BaseTests


class JobConnectorsTest(unittest.TestCase):
    setUp = BaseTests.setUp
    tearDown = BaseTests.tearDown
    job = BaseTests.job

    def source(self, provider):
        return {'id': provider, 'provider': provider, 'board': 'Talan', 'max_pages': 3}

    def gob(self, suffix='1', countries=None):
        return {'id': suffix, 'attributes': {'title': 'Python Engineer', 'countries': countries or ['Colombia'],
            'remote': False, 'remote_modality': 'hybrid', 'published_at': 1700000000,
            'description': '<p>Python SQL</p>', 'functions': '<p>Build APIs</p>', 'benefits': 'Training',
            'min_salary': 1000, 'max_salary': 2000,
            'company': {'data': {'id': 'synthetic', 'attributes': {'name': 'Synthetic'}}},
            'location_cities': {'data': [{'attributes': {'name': 'Bogotá', 'country': 'Colombia'}}]}},
            'links': {'public_url': 'https://www.getonbrd.com/jobs/synthetic-' + suffix}}

    def smart(self, suffix='1', visibility='PUBLIC'):
        return {'id': suffix, 'name': 'Python Engineer', 'visibility': visibility, 'active': True,
            'company': {'name': 'Synthetic'}, 'postingUrl': 'https://jobs.smartrecruiters.com/Talan/' + suffix,
            'releasedDate': '2026-11-20', 'location': {'city': 'Bogotá', 'country': 'co', 'remote': False, 'hybrid': True},
            'jobAd': {'sections': {'jobDescription': {'title': 'Role', 'text': '<p>Python SQL</p>'}}}}

    def test_getonbrd_pagination_expansion_and_public_links(self):
        with patch.object(app, 'fetch', side_effect=[{'data': [self.gob()], 'meta': {'total_pages': 2}},
                {'data': [self.gob('2')], 'meta': {'total_pages': 2}}]) as fetch, patch.object(app.time, 'sleep'):
            batch = app.collect(self.source('getonbrd'))
        self.assertEqual(len(batch), 2)
        self.assertIn('country_code=co', fetch.call_args_list[0].args[0])
        self.assertIn('expand%5B%5D=location_cities', fetch.call_args_list[0].args[0])
        self.assertIn('page=2', fetch.call_args_list[1].args[0])
        self.assertEqual(batch[0]['mode'], 'Híbrido')
        self.assertIn('Bogotá', batch[0]['location'])
        self.assertIn('Build APIs', batch[0]['description'])
        self.assertIn('moneda y período por confirmar', batch[0]['salary'])
        self.assertNotIn('USD', batch[0]['salary'])
        self.assertEqual(batch[0]['company_url'], 'https://www.getonbrd.com/companies/synthetic')

    def test_getonbrd_remote_local_without_country_is_not_colombian(self):
        row = self.gob(countries=['Remote'])
        row['attributes'].update(location_cities={'data': []}, remote=True, remote_modality='remote_local')
        with patch.object(app, 'fetch', return_value={'data': [row], 'meta': {'total_pages': 1}}):
            self.assertEqual(app.collect(self.source('getonbrd')), [])

    def test_getonbrd_invalid_records_are_partial_and_unsafe_links_rejected(self):
        unsafe = self.gob('unsafe'); unsafe['links']['public_url'] = 'https://evil.example/job'
        with patch.object(app, 'fetch', return_value={'data': [self.gob(), {}, unsafe], 'meta': {'total_pages': 1}}):
            batch = app.collect(self.source('getonbrd'))
        self.assertEqual((len(batch), len(batch.rejected)), (1, 2))

    def test_getonbrd_repeated_page_is_a_failure(self):
        with patch.object(app, 'fetch', return_value={'data': [self.gob()], 'meta': {'total_pages': 4}}), patch.object(app.time, 'sleep'):
            with self.assertRaisesRegex(ValueError, 'repitió'):
                app.collect(self.source('getonbrd'))

    def test_getonbrd_failed_page_preserves_previous_batch_and_tracking(self):
        previous = self.job(source='getonbrd'); app.store([previous], 'getonbrd')
        workspace.update_tracking(app.connect, {'id': previous['id'], 'favorite': True, 'notes': 'Keep'})
        with patch.object(app, 'sources', return_value=[dict(self.source('getonbrd'), enabled=True)]), \
             patch.object(app, 'fetch', side_effect=[{'data': [self.gob()], 'meta': {'total_pages': 2}}, ValueError('Offline')]), patch.object(app.time, 'sleep'):
            result = app.sync()
        self.assertIn('error', result['results'][0])
        saved = workspace.detail(app.connect, previous['id'])
        self.assertEqual((saved['notes'], saved['favorite'], saved['active']), ('Keep', True, True))

    def test_stale_getonbrd_hidden_without_calling_it_expired_or_losing_tracking(self):
        job = dict(self.job(), refresh_before=time.time() - 1)
        app.store([job], 'test')
        self.assertEqual(workspace.query(app.connect, {})['total'], 0)
        workspace.update_tracking(app.connect, {'id': job['id'], 'favorite': True})
        self.assertEqual(workspace.query(app.connect, {'view': ['tracking']})['total'], 1)
        self.assertEqual(workspace.detail(app.connect, job['id'])['availability'], 'Actualización pendiente')

    def test_smartrecruiters_details_only_for_public_postings(self):
        public, internal = self.smart(), self.smart('2', 'INTERNAL')
        with patch.object(app, 'fetch', side_effect=[{'content': [public, internal], 'totalFound': 2}, public]) as fetch, patch.object(app.time, 'sleep'):
            batch = app.collect(self.source('smartrecruiters'))
        self.assertEqual(len(batch), 1)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(fetch.call_args_list[1].args[0], 'https://api.smartrecruiters.com/v1/companies/Talan/postings/1')
        self.assertIn('Python SQL', batch[0]['description'])
        self.assertEqual((batch[0]['location'], batch[0]['mode']), ('Bogotá, Colombia', 'Híbrido'))

    def test_smartrecruiters_detail_failure_does_not_return_partial_batch(self):
        with patch.object(app, 'fetch', side_effect=[{'content': [self.smart()], 'totalFound': 1}, ValueError('Offline')]):
            with self.assertRaisesRegex(ValueError, 'Offline'):
                app.collect(self.source('smartrecruiters'))

    def test_jooble_configuration_never_serializes_key_and_toggles_only_that_source(self):
        secret = 'synthetic-key-for-tests'
        with patch.dict(os.environ, {'JOOBLE_API_KEY': ''}):
            source = next(s for s in app.sources() if s['id'] == 'jooble')
            self.assertFalse(source['enabled'])
            self.assertEqual(source['integration_status'], 'needs_key')
            with self.assertRaisesRegex(ValueError, 'Falta la clave'):
                job_connectors.jooble_search({})
        with patch.dict(os.environ, {'JOOBLE_API_KEY': secret}):
            catalogue = app.sources()
            self.assertTrue(next(s for s in catalogue if s['id'] == 'jooble')['enabled'])
            self.assertNotIn(secret, json.dumps(catalogue))

    def test_local_jooble_key_survives_restart_without_metadata_or_backup_leak(self):
        with patch.dict(os.environ, {'JOOBLE_API_KEY': ''}):
            secret = 'local-synthetic-secret'
            path = app.DB.parent / 'jooble-private.json'
            path.write_text(json.dumps({'key': secret}))
            source = next(s for s in app.sources() if s['id'] == 'jooble')
            self.assertTrue(source['enabled'])
            self.assertNotIn(secret, json.dumps(source))
            self.assertNotIn(secret, json.dumps(workspace.backup(app.connect)))
            with patch.object(job_connectors, 'jooble_search', return_value={'jobs': []}) as search:
                app.collect(source)
                self.assertEqual(search.call_args.kwargs['key'], secret)

    def test_jooble_errors_do_not_disclose_credentials(self):
        secret = 'synthetic-secret-key'
        with patch.dict(os.environ, {'JOOBLE_API_KEY': secret}), \
             patch.object(job_connectors, 'urlopen', side_effect=URLError('https://co.jooble.org/api/' + secret)):
            with self.assertRaises(ValueError) as failure:
                job_connectors.jooble_search({})
        self.assertNotIn(secret, str(failure.exception))

    def test_jooble_deduplicates_queries_and_limits_geography(self):
        jobs = [{'title': 'Python Engineer', 'company': 'Synthetic', 'location': 'Bogotá, Colombia', 'link': 'https://example.com/1'},
                {'title': 'Python Engineer', 'location': 'US only', 'link': 'https://example.com/2'}]
        with patch.object(job_connectors, 'jooble_search', return_value={'jobs': jobs}) as search:
            batch = app.collect(dict(self.source('jooble'), queries=['python', 'datos']))
        self.assertEqual(len(batch), 1)
        self.assertEqual(search.call_count, 2)
        self.assertEqual(search.call_args.args[0]['location'], 'Bogotá, Colombia')


    def test_partial_empty_catalog_preserves_previous_jobs(self):
        source = dict(self.source('smartrecruiters'), enabled=True, partial_catalog=True, country_filter=False)
        previous = self.job(source='smartrecruiters'); app.store([previous], 'smartrecruiters')
        with patch.object(app, 'sources', return_value=[source]), patch.object(app, 'fetch', return_value={'content': [], 'totalFound': 0}):
            result = app.sync()
        self.assertTrue(result['results'][0]['partial'])
        self.assertTrue(workspace.detail(app.connect, previous['id'])['active'])

    def test_inactive_public_detail_is_not_an_open_vacancy(self):
        source = dict(self.source('smartrecruiters'), seed_postings=['1'], partial_catalog=True, country_filter=False)
        closed = self.smart(); closed['active'] = False
        with patch.object(app, 'fetch', side_effect=[{'content': [], 'totalFound': 0}, closed]):
            batch = app.collect(source)
        self.assertEqual(len(batch), 0)
        self.assertTrue(batch.partial)

    def test_smartrecruiters_punctuation_location_uses_city_country(self):
        row = self.smart(); row['location']['fullLocation'] = ', '
        parsed = job_connectors.smartrecruiters_record(self.source('smartrecruiters'), row, app.normalize, app.valid_url)
        self.assertEqual(parsed['location'], 'Bogotá, Colombia')


del BaseTests
