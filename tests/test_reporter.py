import json
from tempfile import NamedTemporaryFile
from unittest import TestCase

from cloudweatherreport.reporter import Reporter


class TestReporter(TestCase):

    def test_generate_html(self):
        r = Reporter(None, None, None)
        with NamedTemporaryFile() as html_file:
            html_output = r.generate_html(
                json_content=self.make_json(), output_file=html_file.name)
            content = html_file.read()
        self.assertRegexpMatches(html_output, '1.55')
        self.assertRegexpMatches(html_output, '3.55')
        self.assertRegexpMatches(content, '1.55')
        self.assertRegexpMatches(content, '3.55')

    def test_generate_json(self):
        results = self.make_results()
        reporter = Reporter(bundle='git', results=results, options=None)
        with NamedTemporaryFile() as json_file:
            json_result = reporter.generate_json(output_file=json_file.name)
            json_result = json.loads(json_result)
            content = json_file.read()
        self.maxDiff = None
        for result in json_result["results"]:
            self.assertIn(result["cloud"], ['aws', 'joyent'])
            for test in result["tests"]:
                self.assertIn(test["name"],
                              ['charm-proof', '00-setup', '10-actions'])
        self.assertIn('"name": "charm-proof"', content)

    def test_generate(self):
        results = self.make_results()
        reporter = Reporter(bundle='git', results=results, options=None)
        with NamedTemporaryFile() as json_file:
            with NamedTemporaryFile() as html_file:
                reporter.generate(
                    html_filename=html_file.name, json_filename=json_file.name)
                json_content = json_file.read()
                html_content = html_file.read()
        json_content = json.loads(json_content)
        self.assertIn('charm-proof', html_content)
        self.assertEqual(json_content["bundle"]["name"], 'git')

    def make_results(self):
        return [
            {
                'env_name': 'aws',
                'action_results': [{'repo': '/tmp/a'}, {'users': 'the dude'}],
                'test_results': {
                    'tests': [
                        {'returncode': 0,
                         'test': 'charm-proof',
                         'output': 'foo',
                         'duration': 1.55,
                         'suite': 'git',
                         },
                        {'returncode': 0,
                         'test': '00-setup',
                         'output': 'foo',
                         'duration': 2.55,
                         'suite': 'git'},
                        {'returncode': 1,
                         'test': '10-actions',
                         'duration': 3.55,
                         'suite': 'git',
                         }
                    ],
                },
            },
            {
                'env_name': 'joyent',
                'action_results': [{'repo': '/tmp/a'}, {'users': 'the dude'}],
                'test_results': {
                    'tests': [
                        {'returncode': 0,
                         'test': 'charm-proof',
                         'output': 'foo',
                         'duration': 1,
                         'suite': 'git',
                         },
                        {'returncode': 0,
                         'test': '00-setup',
                         'output': 'foo',
                         'duration': 2,
                         'suite': 'git'},
                        {'returncode': 1,
                         'test': '10-actions',
                         'duration': 3,
                         'suite': 'git',
                         }
                    ],
                },
            }]

    def make_json(self):
        return """{
            "version": 1,
            "results": [
                {
                    "tests": [
                        {
                            "duration": 1.55,
                            "name": "charm-proof",
                            "result": "PASS"
                        },
                        {
                            "duration": 2.55,
                            "name": "00-setup",
                            "result": "PASS"
                        },
                        {
                            "duration": 3.55,
                            "name": "10-actions",
                            "result": "PASS"
                        }
                    ],
                    "cloud": "aws"
                },
                {
                    "tests": [
                        {
                            "duration": 1,
                            "name": "charm-proof",
                            "result": "PASS"
                        },
                        {
                            "duration": 2,
                            "name": "00-setup",
                            "result": "PASS"
                        },
                        {
                            "duration": 3,
                            "name": "10-actions",
                            "result": "PASS"
                        }
                    ],
                    "cloud": "joyent"
                }
            ],
            "bundle": {
                "services": null,
                "name": "git",
                "relations": null,
                "machines": null
            }
        }"""
