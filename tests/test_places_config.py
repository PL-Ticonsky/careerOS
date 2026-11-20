import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import places_config


class PlacesConfigTest(unittest.TestCase):
    def test_local_secret_permissions_and_public_status(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'GOOGLE_PLACES_API_KEY': ''}):
            db = Path(folder) / 'test.db'
            secret = 'AIza' + 'x' * 35
            self.assertEqual(places_config.status(db), {'configured': False, 'source': 'none'})
            status = places_config.save(db, {'key': secret})
            self.assertEqual(status, {'configured': True, 'source': 'local'})
            self.assertEqual(places_config.key(db), secret)
            self.assertNotIn(secret, json.dumps(status))
            self.assertEqual((Path(folder) / 'places-private.json').stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(Path(folder).glob('.places-*')), [])

    def test_invalid_key_never_writes_and_environment_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / 'test.db'
            with patch.dict(os.environ, {'GOOGLE_PLACES_API_KEY': ''}):
                for key in [None, '', 'invalid', [], 'AIza' + '../bad' * 10]:
                    with self.assertRaises(ValueError): places_config.save(db, {'key': key})
                self.assertFalse((Path(folder) / 'places-private.json').exists())
            with patch.dict(os.environ, {'GOOGLE_PLACES_API_KEY': 'environment-secret'}):
                self.assertEqual(places_config.status(db)['source'], 'environment')
                with self.assertRaises(ValueError): places_config.save(db, {'key': 'AIza' + 'x' * 35})
