import unittest

import app
import call_center
import workspace


class CallCenterTest(unittest.TestCase):
    def check(self, title, location, modality='', description=''):
        item = app.normalize('test', title, 'Empresa', location, 'https://example.org/job',
                             description, mode=modality)
        item['mode'] = call_center.mode(item)
        return call_center.matches(item, workspace.local_market(item))

    def test_matching_role_and_explicit_workplace(self):
        self.assertTrue(self.check('Agente call center', 'Bogotá', description='Modalidad: Presencial'))
        self.assertTrue(self.check('Contact Center Agent (Remote)', 'Colombia'))
        self.assertFalse(self.check('Call Center — proceso virtual', 'Bogotá'))
        self.assertFalse(self.check('Call center presencial', 'Medellín, Colombia'))
        self.assertFalse(self.check('Call center híbrido', 'Bogotá', 'Remoto'))
        self.assertFalse(self.check('Agente call center remoto', 'México'))
        self.assertFalse(self.check('Customer service associate', 'Bogotá', 'Presencial'))
        self.assertFalse(self.check('Software engineer', 'Bogotá', 'Presencial', 'Call center experience'))

    def test_source_only_appears_in_call_center_feed(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        with TemporaryDirectory() as directory, patch.object(app, 'DB', Path(directory) / 'test.db'):
            app.init()
            job = app.normalize(call_center.SOURCE, 'Call center agent', 'Empresa', 'Bogotá',
                                'https://example.org/job', mode='Presencial')
            app.store([job], call_center.SOURCE)
            self.assertEqual(workspace.query(app.connect, {'view': ['empleo']})['total'], 0)
            self.assertEqual(workspace.query(app.connect, {'view': ['empleo'], 'callcenter': ['1']})['total'], 1)
            workspace.update_tracking(app.connect, {'id': job['id'], 'favorite': True})
            self.assertEqual(workspace.query(app.connect, {'view': ['tracking']})['total'], 1)
