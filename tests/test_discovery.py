import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs
import app
import discovery
import workspace
from test_app import CareerOSTest as BaseTests


class DiscoveryTests(unittest.TestCase):
    setUp = BaseTests.setUp
    tearDown = BaseTests.tearDown

    def event(self, **changes):
        row = {'@type': 'Event', 'name': 'Python Bogotá', 'url': 'https://example.com/event', 'startDate': '2027-01-01T18:00:00-05:00',
               'location': {'@type': 'Place', 'address': {'addressLocality': 'Bogotá'}}, 'organizer': {'name': 'Community'}}
        row.update(changes); return row

    def test_physical_only_bogota_and_explicit_remote(self):
        for location, allowed in [('Bogotá', True), ('Bogota, Colombia', True), ('Medellín', False), ('Mosquera', False), ('', False)]:
            row = self.event(location=location)
            self.assertEqual(discovery.structured_event({'id':'test'},row,app.normalize) is not None, allowed)
        remote = discovery.structured_event({'id':'test'},self.event(location={'@type':'VirtualLocation','url':'https://example.com/join'}),app.normalize)
        self.assertEqual(remote['mode'],'Remoto')
        self.assertIsNone(discovery.structured_event({'id':'test'},self.event(eventStatus='https://schema.org/EventCancelled'),app.normalize))

    def test_geo_filter_applies_to_existing_records_and_separate_announcements(self):
        for name,mode,location in [('local','Presencial','Bogotá'),('foreign','Presencial','Madrid'),('online','Remoto','Online'),('hybrid','Híbrido','Medellín')]:
            item=app.normalize('test',name,'',location,'https://example.com/'+name,mode=mode,kind='evento')
            app.store([item],'test',False)
        item=app.normalize('test','Oracle certification','','Por confirmar','https://example.com/course',kind='evento')
        item.update(discovery_only=True,event_type='Formación / certificaciones')
        app.store([item],'test',False)
        result=workspace.query(app.connect,parse_qs('view=evento'))
        self.assertEqual({i['title'] for i in result['items']},{'local','online'})
        result=workspace.query(app.connect,parse_qs('view=evento&discovery=1'))
        self.assertEqual([i['title'] for i in result['items']],['Oracle certification'])

    def test_public_page_extraction_dedup_and_partial(self):
        row=self.event(isAccessibleForFree=True)
        page='<script type="application/ld+json">'+json.dumps({'@graph':[row,row]})+'</script><a href="https://evil.example/events/2">ignore</a>'
        batch=discovery.collect_web({'id':'test','url':'https://example.com/','link_pattern':'events'},app.normalize,app.Batch,lambda url:page)
        self.assertEqual(len(batch),1); self.assertEqual(batch[0]['cost'],'Gratis')
        self.assertEqual(batch[0]['event_end_date'],'2027-01-01')
        with self.assertRaises(ValueError): discovery.collect_web({'id':'test','url':'https://example.com/'},app.normalize,app.Batch,lambda url:'Blocked')

    def test_official_announcement_is_not_free_exam_or_open_registration(self):
        page='<title>Cursos de Oracle gratis</title><p>Inscripciones históricas</p><script type="application/ld+json">'+json.dumps(self.event())+'</script>'
        batch=discovery.collect_web({'id':'test','name':'District','url':'https://example.com/','announcements':True,'known_deadline':'2026-08-07'},app.normalize,app.Batch,lambda url:page)
        self.assertTrue(batch[0]['discovery_only']); self.assertNotIn('cost',batch[0])
        self.assertEqual(batch[0]['event_end_date'],'2026-08-07')
        self.assertEqual(batch[0]['mode'],'Por confirmar')
        app.store(batch,'test'); workspace.validate_backup(workspace.backup(app.connect),app.valid_url)

    def test_non_technical_district_news_is_ignored(self):
        with self.assertRaises(ValueError):
            discovery.collect_web({'id':'test','name':'District','url':'https://example.com/','announcements':True},app.normalize,app.Batch,
                                  lambda url:'<title>Noticias de cursos de belleza | Bogotá</title><p>Inscríbete</p>')

    def test_online_country_restrictions_are_not_assumed_accessible(self):
        self.assertFalse(discovery.eligible_event({'mode':'Remoto','location':'Online · US only'}))
        self.assertTrue(discovery.eligible_event({'mode':'Remoto','location':'Online','requirements':'Solo residentes de Bogotá'}))

    def test_places_requires_key_and_valid_inputs(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(ValueError,'GOOGLE_PLACES_API_KEY'): discovery.places_search({'query':'Cafe'})
        for data in [{},{'query':[]},{'query':'x'},{'query':'Cafe','area':[]}]:
            with self.assertRaises(ValueError): discovery.places_search(data)

    def test_places_filters_city_and_missing_website_without_exposing_key(self):
        def place(pid,city='Bogotá',**extra):
            return dict(id=pid,displayName={'text':'Cafe'},addressComponents=[{'longText':city,'types':['locality']}],googleMapsUri='https://maps.google.com/?cid=1',**extra)
        rows=[place('yes'),place('web',websiteUri='https://example.com'),place('outside','Chía'),place('closed',businessStatus='CLOSED_PERMANENTLY')]
        def opener(request,timeout):
            self.assertEqual(request.get_header('X-goog-api-key'),'test-secret')
            self.assertIn('places.websiteUri',request.get_header('X-goog-fieldmask'))
            self.assertIn('nextPageToken',request.get_header('X-goog-fieldmask'))
            self.assertIn('places.attributions',request.get_header('X-goog-fieldmask'))
            self.assertIn('locationRestriction',json.loads(request.data))
            return io.BytesIO(json.dumps({'places':rows,'nextPageToken':'next'}).encode())
        with patch.dict(os.environ,{'GOOGLE_PLACES_API_KEY':'test-secret'}):
            result=discovery.places_search({'query':'Cafe'},opener)
        self.assertEqual([i['place_id'] for i in result['items']],['yes'])
        self.assertEqual(result['next_page_token'],'next'); self.assertNotIn('test-secret',json.dumps(result))


del BaseTests
