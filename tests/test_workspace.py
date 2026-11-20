import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from urllib.parse import parse_qs
from unittest.mock import patch

import app
import workspace
from career_rules import eligibility, matches


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = app.DB
        app.DB = Path(self.temp.name) / 'workspace.db'
        app.init()

    def tearDown(self):
        app.DB = self.old
        self.temp.cleanup()

    def job(self, source='a', suffix='1', **kwargs):
        return app.normalize(source, kwargs.get('title', 'Python Engineer'), 'Synthetic',
                             kwargs.get('location', 'Colombia'), 'https://example.com/' + suffix,
                             kwargs.get('description', 'Python SQL'), published=kwargs.get('published', '2026-01-01'))

    def test_exclusions_and_skills_with_punctuation(self):
        for location in ['Worldwide except Colombia', 'Global, excluding LATAM', 'Solo Estados Unidos y Colombia', 'Latin America excluding Colombia', 'No Colombia', 'Not Colombia', 'US only', 'Nottingham, UK']:
            self.assertEqual(eligibility(location), 'Por confirmar', location)
        self.assertEqual(eligibility('Bogotá, Colombia'), 'Compatible por ubicación')
        self.assertEqual(matches('C++ and .NET, not C# or javascript', ['c++', '.net', 'java']), ['c++', '.net'])

    def test_favorite_does_not_erase_stage_notes_or_history(self):
        item = self.job(); app.store([item], 'a')
        workspace.update_tracking(app.connect, {'id': item['id'], 'status': 'Entrevista', 'notes': 'Keep', 'next_action': 'Prepare', 'due_date': '2027-01-01'})
        workspace.update_tracking(app.connect, {'id': item['id'], 'favorite': True})
        workspace.update_tracking(app.connect, {'id': item['id'], 'favorite': False})
        saved = workspace.detail(app.connect, item['id'])
        self.assertEqual((saved['status'], saved['notes'], saved['next_action'], saved['due_date']), ('Entrevista', 'Keep', 'Prepare', '2027-01-01'))
        self.assertEqual(len(saved['timeline']), 1)
        workspace.update_tracking(app.connect, {'id': item['id'], 'status': 'Entrevista'})
        self.assertEqual(len(workspace.detail(app.connect, item['id'])['timeline']), 1)

    def test_cross_source_provenance_and_fallback(self):
        item = self.job(); app.store([item], 'a')
        app.store([dict(item, source='b', title='Other source title')], 'b')
        self.assertEqual(workspace.detail(app.connect, item['id'])['title'], item['title'])
        app.store([], 'a')
        saved = workspace.detail(app.connect, item['id'])
        self.assertTrue(saved['active']); self.assertEqual(saved['source'], 'b')
        self.assertEqual(len(saved['sources']), 2)
        app.store([], 'b')
        self.assertEqual(workspace.detail(app.connect, item['id'])['availability'], 'Fuera del lote')

    def test_manual_duplicate_cannot_overwrite(self):
        item = self.job(); app.store([item], 'a')
        app.store([dict(item, source='manual', title='Changed')], 'manual', False)
        saved = workspace.detail(app.connect, item['id'])
        self.assertEqual(saved['title'], item['title']); self.assertEqual(saved['source'], 'a')
        self.assertEqual(len(saved['sources']), 1)

    def test_expiry_distinct_from_missing_and_tracking_accessible(self):
        expired = dict(self.job(), expires=1)
        app.store([expired], 'a')
        self.assertEqual(workspace.detail(app.connect, expired['id'])['availability'], 'Vencida')
        self.assertEqual(workspace.query(app.connect, {})['total'], 0)
        workspace.update_tracking(app.connect, {'id': expired['id'], 'favorite': True})
        self.assertEqual(workspace.query(app.connect, {'view': ['tracking']})['total'], 1)
        app.store([], 'a')
        self.assertEqual(workspace.detail(app.connect, expired['id'])['availability'], 'Vencida')

    def test_pagination_filters_personal_profile_and_duplicates(self):
        app.store([self.job(suffix=str(n), description='Rust ' + ('Python' if n % 2 else '')) for n in range(30)], 'a')
        workspace.save_profile(app.connect, {'skills': ['Rust'], 'mode': 'Remoto', 'level': 'Senior', 'location': 'Bogotá'})
        first = workspace.query(app.connect, parse_qs('limit=10&sort=company&ungrouped=1'))
        second = workspace.query(app.connect, parse_qs('limit=10&offset=10&sort=company&ungrouped=1'))
        self.assertEqual((first['total'], len(first['items'])), (30, 10))
        self.assertTrue(first['has_more'])
        self.assertFalse({j['id'] for j in first['items']} & {j['id'] for j in second['items']})
        self.assertNotIn('description', first['items'][0]); self.assertNotIn('notes', first['items'][0])
        self.assertEqual(first['items'][0]['skills'], ['rust'])
        self.assertEqual(first['items'][0]['duplicate_count'], 29)
        self.assertEqual(workspace.query(app.connect, parse_qs('query=python&ungrouped=1'))['total'], 30)  # title
        self.assertEqual(workspace.query(app.connect, parse_qs('location=Bogota'))['total'], 0)
        self.assertEqual(len(workspace.detail(app.connect, first['items'][0]['id'])['duplicates']), 20)

    def test_feed_groups_before_pagination_and_keeps_originals(self):
        app.store([self.job(suffix=str(n), title=f'Role {n // 3}') for n in range(9)], 'a')
        first = workspace.query(app.connect, parse_qs('limit=2&sort=company'))
        second = workspace.query(app.connect, parse_qs('limit=2&offset=2&sort=company'))
        self.assertEqual((first['total'], first['raw_total'], first['grouped_duplicates']), (3, 9, 6))
        self.assertEqual([j['group_count'] for j in first['items']], [3, 3])
        self.assertEqual(len(second['items']), 1)
        self.assertFalse({j['title'] for j in first['items']} & {j['title'] for j in second['items']})
        variants = workspace.detail(app.connect, first['items'][0]['id'])['grouped_variants']
        self.assertEqual(len(variants), 3)
        self.assertEqual(len({j['url'] for j in variants}), 3)
        self.assertEqual(workspace.query(app.connect, parse_qs('ungrouped=1'))['total'], 9)

    def test_feed_groups_respect_location_mode_kind_and_unknown_company(self):
        base = self.job()
        jobs = [base, dict(self.job(suffix='2'), location='Bogotá, Colombia'),
                dict(self.job(suffix='3'), mode='Presencial'),
                dict(self.job(suffix='4'), kind='freelance'),
                dict(self.job(suffix='5'), company=''), dict(self.job(suffix='6'), company='')]
        app.store(jobs, 'a')
        self.assertEqual(workspace.query(app.connect, {})['total'], 5)
        self.assertEqual(workspace.query(app.connect, parse_qs('view=freelance'))['total'], 1)

    def test_group_representative_matches_filters_and_sort(self):
        old = self.job(suffix='old', description='Python', published='2026-01-01')
        new = self.job(suffix='new', description='Rust', published='2026-11-01')
        app.store([old], 'a'); app.store([new], 'b')
        self.assertEqual(workspace.query(app.connect, parse_qs('sort=recent'))['items'][0]['id'], new['id'])
        self.assertEqual(workspace.query(app.connect, parse_qs('source=a'))['items'][0]['id'], old['id'])
        self.assertEqual(workspace.query(app.connect, parse_qs('query=rust'))['items'][0]['id'], new['id'])
        self.assertEqual(workspace.query(app.connect, parse_qs('query=rust'))['items'][0]['group_count'], 1)

    def test_handled_group_hidden_but_tracking_and_opt_in_keep_records(self):
        jobs = [self.job(suffix=str(n)) for n in range(2)]
        app.store(jobs, 'a')
        workspace.update_tracking(app.connect, {'id': jobs[0]['id'], 'favorite': True, 'notes': 'keep'})
        self.assertEqual(workspace.query(app.connect, {})['total'], 0)
        self.assertEqual(workspace.query(app.connect, parse_qs('ungrouped=1'))['total'], 0)
        self.assertEqual(workspace.query(app.connect, parse_qs('view=tracking'))['total'], 1)
        self.assertEqual(workspace.query(app.connect, parse_qs('show_saved=1'))['total'], 1)
        self.assertEqual(workspace.query(app.connect, parse_qs('favorite=1'))['items'][0]['id'], jobs[0]['id'])
        workspace.update_tracking(app.connect, {'id': jobs[0]['id'], 'favorite': False})
        self.assertEqual(workspace.query(app.connect, {})['total'], 1)
        for stage in ['Guardada', 'Postulada', 'Entrevista', 'Oferta', 'Descartada']:
            workspace.update_tracking(app.connect, {'id': jobs[0]['id'], 'status': stage})
            self.assertEqual(workspace.query(app.connect, {})['total'], 0, stage)
        self.assertEqual(workspace.detail(app.connect, jobs[0]['id'])['notes'], 'keep')

    def test_tracking_does_not_collapse_distinct_saved_variants(self):
        jobs = [self.job(suffix=str(n)) for n in range(2)]
        app.store(jobs, 'a')
        for j in jobs:
            workspace.update_tracking(app.connect, {'id': j['id'], 'status': 'Guardada'})
        self.assertEqual(workspace.query(app.connect, parse_qs('view=tracking'))['total'], 2)

    def test_colombia_market_and_bogota_priority_are_conservative(self):
        locations = ['Worldwide', 'Medellín, Colombia', 'Bogotá', 'US only', 'Worldwide except Colombia']
        app.store([dict(self.job(suffix=str(n), location=location), mode='Remoto') for n, location in enumerate(locations)], 'a')
        local = workspace.query(app.connect, parse_qs('market=colombia&sort=local'))
        self.assertEqual([j['location'] for j in local['items']], ['Bogotá', 'Medellín, Colombia'])
        self.assertEqual(workspace.query(app.connect, parse_qs('market=bogota'))['total'], 1)
        self.assertEqual(workspace.query(app.connect, parse_qs('market=compatible'))['total'], 3)
        with self.assertRaises(ValueError): workspace.query(app.connect, parse_qs('market=invalid'))

    def test_identical_remote_content_groups_city_and_title_variants(self):
        titles = ['Senior Python/Flask+React Fullstack Engineer - Remote, Latin America',
                  'Senior Software Engineer (Python/Flask+React) - Remote, Latin America']
        jobs = [dict(self.job(suffix=f'{n}-{city}', title=title, location=city, description='Build Python Flask React applications. ' * 20), mode='Remoto')
                for n, title in enumerate(titles) for city in ['Bogotá, Colombia', 'Cali, Colombia', 'Colombia']]
        app.store(jobs, 'a')
        result = workspace.query(app.connect, parse_qs('market=colombia&sort=local'))
        self.assertEqual((result['total'], result['raw_total']), (1, 6))
        self.assertEqual(result['items'][0]['group_count'], 6)
        self.assertEqual(len(result['items'][0]['group_locations']), 3)
        self.assertIn('Bogotá', result['items'][0]['location'])
        detail = workspace.detail(app.connect, result['items'][0]['id'])
        self.assertEqual(len(detail['grouped_variants']), 6)
        self.assertEqual({j['title'] for j in detail['grouped_variants']}, set(titles))
        workspace.update_tracking(app.connect, {'id': jobs[-1]['id'], 'favorite': True})
        self.assertEqual(workspace.query(app.connect, {})['total'], 0)
        self.assertEqual(workspace.query(app.connect, parse_qs('view=tracking'))['total'], 1)
        self.assertEqual(workspace.query(app.connect, parse_qs('show_saved=1'))['total'], 1)

    def test_remote_content_does_not_group_distinct_roles_restrictions_or_content(self):
        base = dict(self.job(suffix='base', title='Senior Python Flask React Engineer',
                    description='Build Python Flask React applications. ' * 20), mode='Remoto', level='Senior')
        jobs = [base]
        for n, changes in enumerate([
            {'description': base['description'] + ' Different responsibilities.'},
            {'location': 'US only'}, {'level': 'Junior'}, {'mode': 'Híbrido'},
            {'salary': '10000 USD / month'}, {'employment_type': 'Contractor'},
            {'title': 'Senior Java Angular Engineer'}, {'company': 'Another employer'}]):
            item = dict(base, id='', url=f'https://example.com/distinct-{n}', **changes)
            import hashlib
            item['id'] = hashlib.sha256(item['url'].encode()).hexdigest()[:24]
            jobs.append(item)
        app.store(jobs, 'a')
        result = workspace.query(app.connect, {})
        self.assertEqual(result['total'], len(jobs))

    def test_matching_prefers_profile_and_dates_sort_consistently(self):
        app.store([self.job(suffix='python', title='Python role', description='Python', published='2026-01-01'),
                   self.job(suffix='rust', title='Rust role', description='Rust', published='2026-10-01T12:00:00Z')], 'a')
        workspace.save_profile(app.connect, {'skills': ['Rust']})
        self.assertEqual(workspace.query(app.connect, {})['items'][0]['title'], 'Rust role')
        self.assertEqual(workspace.query(app.connect, parse_qs('sort=recent'))['items'][0]['title'], 'Rust role')

    def test_due_filter_and_validation(self):
        item = self.job(); app.store([item], 'a')
        workspace.update_tracking(app.connect, {'id': item['id'], 'status': 'Postulada', 'due_date': '2020-01-01'})
        self.assertEqual(workspace.query(app.connect, parse_qs('view=tracking&due=1'))['total'], 1)
        workspace.update_tracking(app.connect, {'id': item['id'], 'status': 'Descartada'})
        self.assertEqual(workspace.query(app.connect, parse_qs('view=tracking&due=1'))['total'], 0)
        for change in [{'due_date': '2027-02-30'}, {'favorite': 1}, {'next_action': []}, {'notes': 'x' * 10001}]:
            with self.assertRaises(ValueError): workspace.update_tracking(app.connect, dict(id=item['id'], **change))

    def test_backup_restore_preserves_unrelated_and_makes_safety_copy(self):
        item = self.job(); app.store([item], 'a')
        workspace.update_tracking(app.connect, {'id': item['id'], 'status': 'Postulada', 'notes': 'Original', 'favorite': True, 'due_date': '2027-01-01'})
        backup = workspace.backup(app.connect)
        workspace.update_tracking(app.connect, {'id': item['id'], 'status': 'Entrevista', 'notes': 'New'})
        app.store([self.job(suffix='2')], 'manual', False)
        preview = workspace.restore_preview(app.connect, backup, app.valid_url)
        self.assertEqual(preview, {'new': 0, 'updated': 1, 'preserved': 1, 'total': 2})
        result = workspace.restore(app.connect, app.DB, backup, app.valid_url)
        restored = workspace.detail(app.connect, item['id'])
        self.assertEqual(restored['notes'], 'Original'); self.assertEqual(restored['status'], 'Postulada')
        self.assertEqual(len(restored['timeline']), 1)
        with closing(sqlite3.connect(result['safety_backup'])) as c:
            self.assertEqual(c.execute('SELECT notes FROM opportunities WHERE id=?', (item['id'],)).fetchone()[0], 'New')
        workspace.restore(app.connect, app.DB, backup, app.valid_url)
        self.assertEqual(len(workspace.detail(app.connect, item['id'])['timeline']), 1)

    def test_reject_malformed_backup_without_mutation(self):
        app.store([self.job()], 'a'); valid = workspace.backup(app.connect)
        invalid = []
        for mutation in [lambda b: b.update(version=2), lambda b: b['opportunities'][0].update(notes=[]),
                         lambda b: b['sightings'].clear(),
                         lambda b: b['opportunities'][0].update(payload='null'),
                         lambda b: b['opportunities'][0].update(payload=b['opportunities'][0]['payload'].replace('https://example.com/1', 'javascript:alert(1)'))]:
            data = copy.deepcopy(valid); mutation(data); invalid.append(data)
        for data in invalid:
            with self.assertRaises(ValueError): workspace.restore(app.connect, app.DB, data, app.valid_url)
        self.assertEqual(workspace.backup(app.connect)['opportunities'], valid['opportunities'])
        self.assertFalse((app.DB.parent / 'backups').exists())

    def test_migration_keeps_legacy_tracking_and_backs_up(self):
        legacy = Path(self.temp.name) / 'legacy.db'; app.DB = legacy
        with closing(sqlite3.connect(legacy)) as c:
            c.execute("CREATE TABLE opportunities(id TEXT PRIMARY KEY,source TEXT,payload TEXT,active INTEGER,seen TEXT,status TEXT,notes TEXT)")
            item = self.job()
            c.execute('INSERT INTO opportunities VALUES(?,?,?,?,?,?,?)', (item['id'], 'a', json.dumps(item), 1, app.now(), 'Entrevista', 'Legacy notes'))
            c.commit()
        app.init(); app.init()
        saved = workspace.detail(app.connect, item['id'])
        self.assertEqual(saved['notes'], 'Legacy notes'); self.assertTrue(saved['favorite'])
        self.assertEqual(saved['timeline'], [])  # Do not fabricate past transitions.
        self.assertEqual(len(list((legacy.parent / 'backups').glob('before-migration-*.db'))), 1)

    def test_operation_lock_protects_same_database(self):
        first = workspace.acquire_operation(app.DB)
        try:
            self.assertIsNotNone(first); self.assertIsNone(workspace.acquire_operation(app.DB))
        finally: workspace.release_operation(first)
        next_lock = workspace.acquire_operation(app.DB)
        self.assertIsNotNone(next_lock); workspace.release_operation(next_lock)

    def test_background_sync_progress_and_single_flight(self):
        import threading
        waiting = threading.Event(); release = threading.Event()
        def collect(source):
            waiting.set(); release.wait(5); return [self.job()]
        with patch.object(app, 'sources', return_value=[{'id': 'a', 'enabled': True}]), patch.object(app, 'collect', side_effect=collect):
            self.assertTrue(app.start_sync()['started']); self.assertTrue(waiting.wait(2))
            try:
                self.assertTrue(app.start_sync()['busy']); self.assertTrue(app.SYNC_PROGRESS['running'])
                self.assertEqual(app.SYNC_PROGRESS['current'], 'a')
            finally:
                release.set()
                self.assertTrue(app.LOCK.acquire(timeout=5)); app.LOCK.release()
        self.assertFalse(app.SYNC_PROGRESS['running']); self.assertEqual(app.SYNC_PROGRESS['completed'], 1)


if __name__ == '__main__':
    unittest.main()
