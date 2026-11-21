import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

import app
import job_portals
import workspace


class JobPortalsTest(unittest.TestCase):
    def source(self, provider='teamtailor_web'):
        return dict(id='test-portal', company='Sofka', provider=provider,
                    url='https://careers.example.com/jobs', board='sofka',
                    allowed_hosts=['careers.example.com'], max_pages=2)

    def job(self, **fields):
        return dict({'@type': 'JobPosting', 'title': 'Python Developer',
                     'description': 'Build APIs', 'datePosted': '2026-11-21',
                     'jobLocation': {'address': {'addressLocality': 'Bogotá', 'addressCountry': 'CO'}}}, **fields)

    def html(self, job):
        return '<script type="application/ld+json">' + json.dumps(job) + '</script>'

    def collect(self, source, fetch=lambda u: {}):
        return job_portals.collect(source, fetch, app.normalize, app.valid_url,
                                   app.Batch, workspace.local_market, lambda n: None)

    def test_structured_country_restrictions_override_office_address(self):
        row = self.job(jobLocationType='TELECOMMUTE',
                       applicantLocationRequirements={'@type': 'Country', 'name': 'United States'})
        item = job_portals.structured_job(self.source(), row,
            'https://careers.example.com/jobs/1-python', app.normalize, app.valid_url)
        self.assertEqual(item['location'], 'United States')
        self.assertEqual(workspace.local_market(item), 0)
        row['applicantLocationRequirements']['name'] = 'Colombia'
        local = job_portals.structured_job(self.source(), row,
            'https://careers.example.com/jobs/1-python', app.normalize, app.valid_url)
        self.assertEqual((local['mode'], workspace.local_market(local)), ('Remoto', 2))

    def test_teamtailor_pagination_details_and_duplicate_links(self):
        pages = {
            'https://careers.example.com/jobs': '<a href="/jobs/1-python">One</a><a href="?page=2">More</a>',
            'https://careers.example.com/jobs?page=2': '<a href="/jobs/1-python">One</a><a href="/jobs/2-python">Two</a><a href="https://evil.example/jobs/3-python">Bad</a>',
            'https://careers.example.com/jobs/1-python': self.html(self.job()),
            'https://careers.example.com/jobs/2-python': self.html(self.job(title='Python Intern')),
        }
        with patch.object(job_portals, 'read_page', side_effect=lambda u: pages[u]) as read:
            batch = self.collect(self.source())
        self.assertEqual(len(batch), 2)
        self.assertEqual(read.call_count, 4)
        self.assertEqual(batch[0]['apply_url'], batch[0]['url'])
        self.assertEqual(batch[1]['level'], 'Junior')

    def test_teamtailor_visible_detail_when_jsonld_is_omitted(self):
        detail = '''<h1>Cloud Engineer</h1>
            <div data-controller="careersite--responsive-video"><p>Build secure Python APIs</p></div>
            <dl><dt>Ubicaciones</dt><dd>Colombia, México</dd>
            <dt>Estado remoto</dt><dd>Completamente remoto</dd></dl>'''
        with patch.object(job_portals, 'read_page', side_effect=[
                '<a href="/jobs/1-cloud">Cloud</a>', detail]):
            batch = self.collect(self.source())
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch[0]['mode'], 'Remoto')
        self.assertEqual(batch[0]['description'], 'Build secure Python APIs')
        self.assertNotIn('cookies', batch[0]['description'])

    def test_truncated_or_malformed_catalog_is_never_a_complete_empty_snapshot(self):
        source = self.source(); source['max_pages'] = 1
        listing = '<a href="/jobs/1-python">One</a><a href="?page=2">More</a>'
        with patch.object(job_portals, 'read_page', side_effect=[listing, self.html(self.job())]):
            batch = self.collect(source)
        self.assertEqual(len(batch), 1)
        self.assertEqual(len(batch.rejected), 1)
        with patch.object(job_portals, 'read_page', return_value='<h1>Site changed</h1>'):
            with self.assertRaises(ValueError):
                self.collect(source)

    def test_recruitee_preserves_country_salary_and_application_url(self):
        source = self.source('recruitee_public')
        row = {'status': 'published', 'title': 'Engineer', 'locations': [{'city': 'Bogotá', 'country': 'Colombia'}],
            'description': 'Python', 'remote': True, 'careers_url': 'https://careers.example.com/o/engineer',
            'careers_apply_url': 'https://careers.example.com/o/engineer/c/new',
            'salary': {'min': 3000000, 'max': 5000000, 'currency': 'COP', 'period': 'month'}}
        batch = self.collect(source, lambda u: {'offers': [row, dict(row, status='draft')]})
        self.assertEqual(len(batch), 1)
        self.assertIn('COP', batch[0]['salary'])
        self.assertTrue(batch[0]['apply_url'].endswith('/c/new'))
        with self.assertRaises(URLError):
            self.collect(source, lambda u: (_ for _ in ()).throw(URLError('Authentication required')))

    def test_workable_location_checked_before_deduplicating_shared_code(self):
        source = self.source('workable_public'); source['allowed_hosts'] = ['apply.workable.com']
        row = dict(title='Engineer', url='https://apply.workable.com/j/ONE', application_url='https://apply.workable.com/j/ONE/apply')
        foreign = dict(row, locations=[{'city': 'Mexico City', 'country': 'Mexico'}])
        local = dict(row, locations=[{'city': 'Bogotá', 'country': 'Colombia'}])
        with patch.object(job_portals, 'read_page', return_value=self.html(self.job())):
            batch = self.collect(source, lambda u: {'jobs': [foreign, local]})
        self.assertEqual(len(batch), 1)
        self.assertIn('Bogotá', batch[0]['location'])

    def test_yc_reads_company_jobs_not_related_jobs_and_requires_details(self):
        source = self.source('yc_public'); source.update(company='Solum Health', board='solum-health',
            url='https://www.ycombinator.com/companies/solum-health/jobs', allowed_hosts=['www.ycombinator.com'])
        job = {'title': 'Engineer', 'url': '/companies/solum-health/jobs/one',
            'location': 'CO / AR / Remote', 'applyUrl': 'https://account.ycombinator.com/apply', 'salaryRange': '$4K / monthly'}
        props = {'component': 'WaasShowJobsPage', 'props': {'company': {'slug': 'solum-health'},
            'jobPostings': [job], 'relatedJobs': [dict(job, title='Unrelated')]}}
        listing = '<div data-page=\'' + json.dumps(props) + '\'></div>'
        with patch.object(job_portals, 'read_page', side_effect=[listing, self.html(self.job())]):
            batch = self.collect(source)
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch[0]['location'], 'Colombia / AR / Remote')
        self.assertEqual(batch[0]['salary'], '$4K / monthly')
        with self.assertRaises(ValueError):
            job_portals.trusted('https://evil.example/apply', ['account.ycombinator.com'], app.valid_url)

    def test_kushki_explicit_empty_catalog_and_changed_format(self):
        source = self.source('kushki_public')
        payload = '0:["$","div",null,{"jobs":[],"departments":[],"locations":[]}]'
        listing = '<script>self.__next_f.push(' + json.dumps([1, payload]) + ')</script>'
        with patch.object(job_portals, 'read_page', return_value=listing):
            self.assertEqual(self.collect(source), [])
        with patch.object(job_portals, 'read_page', return_value='Changed'):
            with self.assertRaises(ValueError):
                self.collect(source)
