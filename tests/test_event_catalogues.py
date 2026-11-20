import json
import unittest

import app
import event_catalogues


class MLHTest(unittest.TestCase):
    def event(self, suffix='1', **fields):
        row = dict(name='Synthetic Hackathon', url='/events/' + suffix + '/prizes',
            startsAt='2027-01-20T12:00:00Z', endsAt='2027-01-21T12:00:00Z',
            formatType='physical', location='Bogotá', venueAddress={'country': 'CO'},
            websiteUrl='https://example.com/registration')
        row.update(fields)
        return row

    def collect(self, rows):
        text = '<script type="application/json" data-page="app">' + json.dumps({'props': {'upcomingEvents': rows}}) + '</script>'
        return event_catalogues.collect_mlh({'id': 'mlh', 'url': 'https://www.mlh.com/seasons/2027/events'},
            app.normalize, app.valid_url, app.Batch, read=lambda _: text)

    def test_only_bogota_physical_and_explicit_online_are_imported(self):
        rows = [self.event(), self.event('2', location='Toronto', venueAddress={'country': 'CA'}),
                self.event('3', formatType='virtual', location='Online', venueAddress={})]
        batch = self.collect(rows)
        self.assertEqual(len(batch), 2)
        self.assertEqual([j['mode'] for j in batch], ['Presencial', 'Remoto'])
        self.assertEqual(batch[0]['registration_url'], 'https://example.com/registration')
        self.assertEqual(batch[0]['cost'], '')
        self.assertEqual(batch[0]['event_end_date'], '2027-01-21')

    def test_incompatible_and_empty_calendars_are_successful_zero_results(self):
        self.assertEqual(self.collect([self.event(location='Toronto', venueAddress={'country': 'CA'})]), [])
        self.assertEqual(self.collect([]), [])

    def test_changed_format_and_invalid_dates_are_failures(self):
        with self.assertRaises(ValueError):
            event_catalogues.collect_mlh({'id': 'mlh', 'url': 'https://www.mlh.com/seasons/2027/events'},
                app.normalize, app.valid_url, app.Batch, read=lambda _: '<html>No events data</html>')
        with self.assertRaises(ValueError): self.collect([self.event(startsAt='invalid')])

    def test_invalid_record_marks_batch_partial_without_discarding_valid_event(self):
        batch = self.collect([self.event(), self.event('2', url='https://evil.example/event')])
        self.assertEqual((len(batch), len(batch.rejected)), (1, 1))
