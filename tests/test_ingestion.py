import unittest
from unittest.mock import patch
from test_app import CareerOSTest as BaseTests
import app

class IngestionTest(unittest.TestCase):
    setUp = BaseTests.setUp
    tearDown = BaseTests.tearDown
    job = BaseTests.job
    def raw(self):return {'title':'Engineer','company_name':'Company','url':'https://example.com/new'}
    def test_adapter_contracts(self):
        cases=[
            ('greenhouse',{'title':'Engineer','absolute_url':'https://example.com/g','location':{'name':'Bogotá'}}),
            ('lever',{'text':'Engineer','hostedUrl':'https://example.com/l','categories':{'location':'Bogotá'},'descriptionPlain':'Python'}),
            ('ashby',{'title':'Engineer','jobUrl':'https://example.com/a','location':'Remote','isRemote':True}),
            ('arbeitnow',{'title':'Engineer','company_name':'Company','url':'https://example.com/ar','created_at':1700000000}),
            ('remoteok',{'position':'Engineer','url':'https://example.com/r'})]
        for provider,row in cases:
            with self.subTest(provider=provider):
                j=app.parse_record(provider,{'id':'test','company':'Company'},row)
                self.assertEqual(j['title'],'Engineer');self.assertTrue(app.valid_url(j['url']))
        row=app.ET.fromstring('<item><title>Company: Engineer</title><link>https://example.com/w</link></item>')
        self.assertEqual(app.parse_record('wwr',{'id':'test'},row)['company'],'Company')

    def test_local_boards_import_only_explicit_colombia_or_bogota(self):
        rows = [dict(title='Engineer', absolute_url=f'https://example.com/{n}', location={'name': loc}, content='Python', first_published='2026-11-01')
                for n, loc in enumerate(['Bogotá', 'Cali, Colombia', 'US only', 'Worldwide', 'Worldwide except Colombia'])]
        with patch.object(app, 'fetch', return_value={'jobs': rows}):
            batch = app.collect({'id':'local', 'company':'Test', 'provider':'greenhouse', 'board':'test', 'market_scope':'colombia'})
        self.assertEqual([j['location'] for j in batch], ['Bogotá', 'Cali, Colombia'])
        self.assertEqual(batch[0]['published'], '2026-11-01')
        self.assertEqual(batch.rejected, [])

    def test_invalid_row_isolated(self):
        with patch.object(app,'fetch',return_value={'jobs':[{},self.raw(),None]}):
            batch=app.collect({'id':'r','provider':'remotive'})
        self.assertEqual(len(batch),1);self.assertEqual(len(batch.rejected),2)
    def test_all_invalid_is_failure(self):
        with patch.object(app,'fetch',return_value={'jobs':[{}]}):
            with self.assertRaises(ValueError):app.collect({'id':'r','provider':'remotive'})
    def test_invalid_response_shape_is_failure(self):
        with patch.object(app,'fetch',return_value={'jobs':{}}):
            with self.assertRaises(ValueError):app.collect({'id':'r','provider':'remotive'})
    def test_partial_keeps_previous_rows_and_records_history(self):
        app.store([self.job(source='r')],'r')
        with patch.object(app,'sources',return_value=[{'id':'r','provider':'remotive','enabled':True}]),patch.object(app,'fetch',return_value={'jobs':[{},self.raw()]}):
            result=app.sync()
        self.assertEqual(result['results'][0]['rejected'],1)
        self.assertEqual(sum(j['active'] for j in app.snapshot()['items']),2)
        self.assertEqual(app.history()[0]['outcome'],'partial')
    def test_error_and_success_history(self):
        with patch.object(app,'sources',return_value=[{'id':'r','enabled':True}]),patch.object(app,'collect',side_effect=ValueError('offline')):
            app.sync();app.sync()
        self.assertEqual(len(app.history()),1);self.assertEqual(app.history()[0]['outcome'],'error')
    def test_pagination_failure_never_stores_partial_pages(self):
        app.store([self.job(source='j')],'j')
        row={'jobTitle':'Engineer','companyName':'Company','url':'https://example.com/new'}
        with patch.object(app,'sources',return_value=[{'id':'j','provider':'jobicy','enabled':True}]),patch.object(app,'fetch',side_effect=[{'jobs':[row],'nextCursor':'next'},ValueError('network')]),patch.object(app.time,'sleep'):
            app.sync()
        items=app.snapshot()['items'];self.assertEqual(len(items),1);self.assertTrue(items[0]['active']);self.assertEqual(app.history()[0]['outcome'],'error')
    def test_history_retention(self):
        for _ in range(1005):app.record_run('r',app.now(),'success')
        with app.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM run_history').fetchone()[0],1000)
        self.assertEqual(len(app.history()),100)
    def test_additive_initialization_keeps_existing_data(self):
        app.store([self.job()],'test');app.init();self.assertEqual(len(app.snapshot()['items']),1)

# Avoid unittest collecting the imported base class a second time.
del BaseTests
