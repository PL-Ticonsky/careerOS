import io
import json
import os
import unittest
from urllib.error import URLError
from unittest.mock import patch

import app
import serpapi_connector as connector
import workspace
from test_app import CareerOSTest as BaseTests


class SerpApiTest(unittest.TestCase):
    setUp = BaseTests.setUp
    tearDown = BaseTests.tearDown

    def source(self, **changes):
        value = {'id': 'serpapi', 'provider': 'serpapi', 'queries': ['Python Bogotá', 'Backend Bogotá'], 'max_pages': 1}
        value.update(changes); return value

    def row(self, **changes):
        value = {'title': 'Python Engineer', 'company_name': 'Synthetic', 'location': 'Bogotá, Colombia',
                 'description': 'Python SQL applications', 'job_id': 'external-id', 'via': 'LinkedIn',
                 'detected_extensions': {'work_from_home': True, 'posted_at': 'Hace 2 días'},
                 'apply_options': [{'title': 'LinkedIn', 'link': 'https://www.linkedin.com/jobs/view/123?utm_source=google_jobs_apply'},
                                   {'title': 'Employer', 'link': 'https://example.com/jobs/123'}]}
        value.update(changes); return value

    def collect(self, source=None):
        return connector.collect(source or self.source(), 's' * 64, app.normalize, app.valid_url,
                                 app.Batch, workspace.local_market, lambda _: None)

    def test_queries_localization_dedup_and_application_options(self):
        with patch.object(connector, 'account', return_value={'total_searches_left': 250}), \
             patch.object(connector, 'request', return_value={'jobs_results': [self.row()]}) as request:
            batch = self.collect()
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch[0]['url'], 'https://www.linkedin.com/jobs/view/123')
        self.assertEqual(len(batch[0]['apply_options']), 2)
        self.assertEqual(batch[0]['discovery_queries'], ['Python Bogotá', 'Backend Bogotá'])
        self.assertEqual(batch[0]['mode'], 'Remoto')
        self.assertEqual(batch[0]['published'], '')
        self.assertEqual(batch[0]['published_label'], 'Hace 2 días')
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.args[0]['gl'], 'co')
        self.assertEqual(request.call_args.args[0]['hl'], 'es')
        self.assertNotIn('start', request.call_args.args[0])

    def test_search_origin_does_not_invent_remote_eligibility(self):
        with patch.object(connector, 'account', return_value={'total_searches_left': 250}), \
             patch.object(connector, 'request', return_value={'jobs_results': [self.row(location='Anywhere')]}):
            self.assertEqual(self.collect(), [])

    def test_quota_preflight_does_not_consume_searches_when_insufficient(self):
        with patch.object(connector, 'account', return_value={'total_searches_left': 1}), patch.object(connector, 'request') as request:
            with self.assertRaisesRegex(ValueError, 'cuota suficiente'): self.collect()
        request.assert_not_called()

    def test_pagination_uses_token_with_fixed_query_and_localization(self):
        with patch.object(connector, 'account', return_value={'total_searches_left': 250}), \
             patch.object(connector, 'request', side_effect=[{'jobs_results': [self.row()], 'serpapi_pagination': {'next_page_token': 'next'}}, {'jobs_results': []}]) as request:
            self.collect(self.source(queries=['Python Bogotá'], max_pages=2))
        first, second = [call.args[0] for call in request.call_args_list]
        self.assertEqual(second, dict(first, next_page_token='next'))

    def test_partial_records_are_diagnosed_without_losing_valid_records(self):
        with patch.object(connector, 'account', return_value={'total_searches_left': 250}), \
             patch.object(connector, 'request', return_value={'jobs_results': [self.row(), {}]}):
            batch = self.collect(self.source(queries=['Python Bogotá']))
        self.assertEqual((len(batch), len(batch.rejected)), (1, 1))

    def test_provider_failure_aborts_batch_and_never_exposes_key(self):
        secret = 's' * 64
        with patch.object(connector, 'urlopen', side_effect=URLError('https://serpapi.com/search?api_key=' + secret)):
            with self.assertRaises(ValueError) as error:
                connector.request({}, secret)
        self.assertNotIn(secret, str(error.exception))
        with patch.object(connector, 'account', return_value={'total_searches_left': 250}), \
             patch.object(connector, 'request', side_effect=[{'jobs_results': [self.row()]}, ValueError('Offline')]):
            with self.assertRaisesRegex(ValueError, 'Offline'): self.collect()

    def test_empty_results_are_valid_but_missing_payload_is_a_failure(self):
        with patch.object(connector, 'urlopen', return_value=io.BytesIO(json.dumps({'error': "Google hasn't returned any results for this query."}).encode())):
            self.assertEqual(connector.request({}, 's' * 64), {'jobs_results': []})
        with patch.object(connector, 'account', return_value={'total_searches_left': 250}), patch.object(connector, 'request', return_value={}):
            with self.assertRaises(ValueError): self.collect()

    def test_private_key_is_not_in_sources_account_status_or_backups(self):
        secret = 's' * 64
        with patch.dict(os.environ, {'SERPAPI_API_KEY': ''}):
            (app.DB.parent / 'serpapi-private.json').write_text(json.dumps({'key': secret}))
            source = next(s for s in app.sources() if s['id'] == 'serpapi')
            self.assertTrue(source['enabled'])
            self.assertNotIn(secret, json.dumps(app.sources()))
            self.assertNotIn(secret, json.dumps(workspace.backup(app.connect)))
        with patch.object(connector, 'request', return_value={'api_key': secret, 'account_email': 'private@example.com', 'total_searches_left': 250}):
            self.assertEqual(connector.account(secret), {'total_searches_left': 250})

    def test_functional_job_fragments_are_preserved(self):
        url = 'https://example.com/careers?utm_source=google#/jobs/123'
        self.assertEqual(connector.listing_link(url, app.valid_url), 'https://example.com/careers#/jobs/123')

    def test_secret_bearing_and_provider_internal_links_are_not_saved(self):
        for url in ['https://serpapi.com/search?api_key=secret', 'https://example.com?api_key=secret', 'javascript:alert(1)']:
            self.assertEqual(connector.listing_link(url, app.valid_url), '')


del BaseTests
