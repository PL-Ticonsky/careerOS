import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app

class CareerOSTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=app.DB;app.DB=Path(self.temp.name)/'test.db';app.init()
    def tearDown(self): app.DB=self.old;self.temp.cleanup()
    def job(self,**kw):
        args=dict(source='test',title='Junior Python Engineer',company='Company',location='Remote US',url='https://example.com/job',description='<p>Python and SQL</p>');args.update(kw);return app.normalize(**args)
    def test_remote_not_automatically_colombia(self):
        j=self.job();self.assertEqual(j['eligibility'],'Por confirmar');self.assertEqual(j['level'],'Junior');self.assertEqual(j['skills'],['python','sql']);self.assertNotIn('<p>',j['description'])
    def test_bogota_accents(self): self.assertEqual(self.job(location='Bogotá, Colombia')['eligibility'],'Compatible por ubicación')
    def test_unsafe_url_rejected(self):
        for u in ['javascript:alert(1)','file:///etc/passwd','https://user:pass@example.com']:
            with self.assertRaises(ValueError):self.job(url=u)
    def test_upsert_preserves_tracking(self):
        j=self.job();app.store([j],'test')
        with app.connect() as c:c.execute('UPDATE opportunities SET status=?,notes=?',('Entrevista','Tuesday'))
        app.store([self.job(title='Updated Python role')],'test');items=app.snapshot()['items']
        self.assertEqual(len(items),1);self.assertEqual(items[0]['status'],'Entrevista');self.assertEqual(items[0]['notes'],'Tuesday');self.assertEqual(items[0]['title'],'Updated Python role')
    def test_missing_from_snapshot_is_inactive_not_deleted(self):
        app.store([self.job()],'test');app.store([],'test');self.assertFalse(app.snapshot()['items'][0]['active'])
    def test_failed_sync_preserves_jobs_and_other_source_continues(self):
        app.store([self.job()],'test')
        with patch.object(app,'sources',return_value=[{'id':'test','enabled':True},{'id':'other','enabled':True}]),patch.object(app,'collect',side_effect=[ValueError('upstream error'),[self.job(source='other',url='https://example.com/other')]]):
            result=app.sync()
        self.assertIn('error',result['results'][0]);self.assertEqual(len(app.snapshot()['items']),2);self.assertTrue(all(x['active'] for x in app.snapshot()['items']))
    def test_cache_avoids_duplicate_calls(self):
        with patch.object(app,'sources',return_value=[{'id':'test','enabled':True}]),patch.object(app,'collect',return_value=[self.job()]) as collect:
            app.sync();app.sync();self.assertEqual(collect.call_count,1)
    def test_manual_insert_does_not_deactivate_others(self):
        app.store([self.job()],'manual',False);app.store([self.job(url='https://example.com/2')],'manual',False);self.assertEqual(sum(j['active'] for j in app.snapshot()['items']),2)
    def test_himalayas_preserves_application_link_and_timezone(self):
        raw={'jobs':[{'title':'Engineer','companyName':'Company','locationRestrictions':[],'timezoneRestrictions':[1,2],'guid':'https://himalayas.app/job/1','applicationLink':'https://himalayas.app/job/1?utm_source=api','pubDate':1700000000,'expiryDate':9999999999}]}
        with patch.object(app,'fetch',return_value=raw),patch.object(app.time,'sleep'):
            jobs=app.collect({'provider':'himalayas','id':'himalayas','max_pages':1})
        self.assertEqual(jobs[0]['apply_url'],raw['jobs'][0]['applicationLink']);self.assertEqual(jobs[0]['eligibility'],'Por confirmar')
    def test_himalayas_expired_jobs_excluded(self):
        with patch.object(app,'fetch',return_value={'jobs':[{'expiryDate':1}]}),patch.object(app.time,'sleep'):
            self.assertEqual(app.collect({'provider':'himalayas','id':'himalayas','max_pages':1}),[])
    def test_jobicy_cursor_pagination(self):
        raw={'jobTitle':'Developer','companyName':'Company','url':'https://jobicy.com/jobs/1'}
        with patch.object(app,'fetch',side_effect=[{'jobs':[raw],'nextCursor':'abc+'},{'jobs':[raw],'nextCursor':None}]) as f,patch.object(app.time,'sleep'):
            jobs=app.collect({'id':'jobicy','provider':'jobicy'})
        self.assertEqual(len(jobs),1);self.assertIn('cursor=abc%2B',f.call_args_list[1].args[0])
    def test_html_is_text(self): self.assertNotIn('<script>',self.job(description='&lt;script&gt;alert(1)&lt;/script&gt;')['description'])

if __name__=='__main__':unittest.main()
