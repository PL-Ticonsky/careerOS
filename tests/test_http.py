import http.client
import json
import os
from unittest.mock import patch
import tempfile
import threading
import unittest
from pathlib import Path
import app

class QuietHandler(app.Handler):
    def log_message(self,*args):pass

class HTTPTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=app.DB;app.DB=Path(self.temp.name)/'http.db';app.init()
        self.server=app.ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();app.DB=self.old;self.temp.cleanup()
    def request(self,path,body=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        try:
            conn.request('GET' if body is None else 'POST',path,None if body is None else json.dumps(body),headers or {'Content-Type':'application/json'})
            r=conn.getresponse();return r.status,json.loads(r.read())
        finally:conn.close()
    def payload(self,**changes):
        body=dict(kind='evento',mode='Presencial',location='Bogotá',title='Synthetic event',url='https://example.com/test',event_date='2027-01-01');body.update(changes);return body
    def test_manual_status_notes_roundtrip(self):
        status,j=self.request('/api/manual',self.payload());self.assertEqual(status,201)
        self.assertEqual(self.request('/api/status',{'id':j['id'],'status':'Guardada','notes':'Keep me'})[0],200)
        self.assertEqual(self.request('/api/status',{'id':j['id'],'status':'Entrevista'})[0],200)
        item=self.request('/api/data')[1]['items'][0];self.assertEqual(item['notes'],'Keep me');self.assertEqual(item['status'],'Entrevista')
    def test_invalid_inputs_return_json_errors(self):
        for change in [dict(title=None),dict(title=' '),dict(company=[]),dict(event_date='2027-02-30'),dict(event_date='20270101'),dict(title='x'*301),dict(url='javascript:alert(1)')]:
            with self.subTest(change=change):
                status,result=self.request('/api/manual',self.payload(**change));self.assertEqual(status,400);self.assertIn('error',result)
    def test_other_origin_rejected(self):
        status,_=self.request('/api/manual',self.payload(),{'Content-Type':'application/json','Origin':'https://example.org'});self.assertEqual(status,403)
    def test_wrong_content_type_rejected(self):
        status,_=self.request('/api/manual',self.payload(),{'Content-Type':'text/plain'});self.assertEqual(status,415)
    def test_unknown_id_and_history(self):
        self.assertEqual(self.request('/api/status',{'id':'a'*24,'status':'Guardada'})[0],404)
        self.assertEqual(self.request('/api/runs'),(200,[]))

    def test_paged_api_detail_and_duplicate_manual(self):
        _, item = self.request('/api/manual', self.payload())
        status, page = self.request('/api/opportunities?view=evento&limit=1')
        self.assertEqual(status, 200); self.assertEqual(page['total'], 1)
        self.assertNotIn('description', page['items'][0]); self.assertNotIn('notes', page['items'][0])
        self.assertEqual(self.request('/api/manual', self.payload(title='Do not replace')),
                         (200, {'duplicate': True, 'id': item['id']}))
        self.assertEqual(self.request('/api/item?id=' + item['id'])[1]['title'], 'Synthetic event')
        self.assertIn('stats', self.request('/api/meta')[1])
        self.assertEqual(self.request('/api/missing')[0], 404)
        for path in ['/api/opportunities?limit=0', '/api/opportunities?offset=-1', '/api/opportunities?sort=garbage']:
            self.assertEqual(self.request(path)[0], 400)

    def test_profile_backup_restore_and_favorites(self):
        _, item = self.request('/api/manual', self.payload())
        self.assertEqual(self.request('/api/status', {'id': item['id'], 'status': 'Entrevista', 'notes': 'Saved'})[0], 200)
        self.assertEqual(self.request('/api/status', {'id': item['id'], 'favorite': True})[0], 200)
        self.assertEqual(self.request('/api/profile', {'skills': ['Python', 'C++'], 'location': 'Bogotá'})[0], 200)
        backup = self.request('/api/backup')[1]
        self.assertEqual(backup['profile']['skills'], ['python', 'c++'])
        self.request('/api/status', {'id': item['id'], 'notes': 'Changed'})
        self.assertEqual(self.request('/api/restore/preview', backup)[1]['updated'], 1)
        self.assertEqual(self.request('/api/restore', backup)[0], 200)
        restored = self.request('/api/item?id=' + item['id'])[1]
        self.assertEqual(restored['notes'], 'Saved'); self.assertTrue(restored['favorite'])
        self.assertEqual(restored['status'], 'Entrevista')
        self.assertEqual(self.request('/api/restore', {'format': 'other'})[0], 400)

    def test_untrusted_host_rejected_for_reads_and_writes(self):
        headers = {'Content-Type': 'application/json', 'Host': f'evil.example:{self.server.server_port}'}
        self.assertEqual(self.request('/api/meta', headers=headers)[0], 403)
        self.assertEqual(self.request('/api/manual', self.payload(), headers)[0], 403)

    def test_places_local_config_never_returns_or_exports_secret(self):
        with patch.dict(os.environ, {'GOOGLE_PLACES_API_KEY': ''}):
            secret = 'AIza' + 's' * 35
            self.assertFalse(self.request('/api/places/status')[1]['configured'])
            status, result = self.request('/api/places/configure', {'key': secret})
            self.assertEqual(status, 200)
            self.assertTrue(result['configured'])
            self.assertNotIn(secret, json.dumps(result))
            self.assertNotIn(secret, json.dumps(self.request('/api/backup')[1]))
            self.assertEqual(self.request('/api/places/configure', {'key': 'invalid'})[0], 400)
            with patch.object(app.discovery, 'places_search', return_value={'items': []}) as search:
                self.assertEqual(self.request('/api/places/search', {'query': 'Barberías'})[0], 200)
                self.assertEqual(search.call_args.kwargs['key'], secret)

    def test_places_reference_save_is_idempotent_and_does_not_copy_provider_data(self):
        data = {'place_id': 'ChIJ-synthetic-12345', 'label': 'Mi prospecto de barbería',
                'name': 'Provider business name', 'address': 'Provider address', 'phone': 'Provider phone'}
        status, result = self.request('/api/places/save', data)
        self.assertEqual(status, 201)
        item = self.request('/api/item?id=' + result['id'])[1]
        self.assertTrue(item['favorite'])
        self.assertEqual(item['title'], data['label'])
        self.assertEqual(item['google_place_id'], data['place_id'])
        self.assertNotIn(data['name'], json.dumps(item))
        self.assertNotIn(data['phone'], json.dumps(item))
        self.assertNotIn(data['address'], json.dumps(item))
        self.assertEqual(self.request('/api/places/save', data), (200, {'id': result['id'], 'duplicate': True}))
        self.assertEqual(self.request('/api/places/save', dict(data, place_id='../invalid'))[0], 400)

    def test_application_analytics_endpoint_and_dates(self):
        item=app.normalize('fixture','Python Engineer','Example','Bogotá','https://example.com/analytics-http')
        app.store([item],'fixture')
        self.assertEqual(self.request('/api/analytics')[1]['total'],0)
        status,_=self.request('/api/status',dict(id=item['id'],status='Postulada',applied_date='2026-01-15',applied_via='LinkedIn'))
        self.assertEqual(status,200)
        status,result=self.request('/api/analytics?stage=Postulada&limit=1')
        self.assertEqual(status,200)
        self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['applied_date'],'2026-01-15')
        self.assertEqual(result['items'][0]['applied_via'],'LinkedIn')
        self.assertEqual(self.request('/api/analytics?period=invalid')[0],400)

    def test_desktop_health_endpoint_has_no_personal_data(self):
        self.assertEqual(self.request('/api/health'),(200,{'app':'careeros','version':1}))
