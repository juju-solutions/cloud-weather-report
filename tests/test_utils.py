import json
import os
from shutil import rmtree
from tempfile import (
    NamedTemporaryFile,
    mkdtemp,
)
from unittest import TestCase

import yaml

from cloudweatherreport.utils import (
    create_bundle_yaml,
    find_unit,
    get_benchmark_data,
    get_all_test_results,
    read_file,
    run_action,
    mkdir_p,
    wait_for_action_complete,
    get_provider_name,
)
from tests.common_test import(
    setup_test_logging,
)


class TestUtil(TestCase):

    def setUp(self):
        setup_test_logging(self)

    def test_read_file(self):
        test_plan = {'tests': ['test1', 'test2'], 'bundle': 'bundle-url'}
        content = yaml.dump(test_plan)
        with NamedTemporaryFile(suffix=".yaml") as yaml_file:
            yaml_file.write(content)
            yaml_file.flush()
            output = read_file(yaml_file.name, file_type='yaml')
        self.assertEqual(output, yaml.load(content))

    def test_read_file_no_deserialize(self):
        test_plan = {'tests': ['test1', 'test2'], 'bundle': 'bundle-url'}
        content = yaml.dump(test_plan)
        with NamedTemporaryFile(suffix=".yaml") as yaml_file:
            yaml_file.write(content)
            yaml_file.flush()
            output = read_file(yaml_file.name)
        self.assertEqual(output, 'bundle: bundle-url\ntests: [test1, test2]\n')

    def test_run_action(self):
        fake_client = FakeActionClient()
        results = run_action(fake_client, 'git/0', 'list-users',  None)
        expected = {'users': 'user, someuser'}
        self.assertEqual(results, expected)
        return results

    def test_wait_for_action_complete(self):
        fake_client = FakeActionClient()
        pending_action = fake_client.enqueue_units('git/0', 'list-users', None)
        result = wait_for_action_complete(
            fake_client, pending_action['results'][0]['action']['tag'])
        expected = {'users': 'user, someuser'}
        self.assertEqual(result['results'][0]['output'], expected)

    def test_wait_for_action_complete_timeout(self):
        fake_client = FakeActionClient()
        pending_action = fake_client.enqueue_units('git/0', 'list-users', None)
        with self.assertRaisesRegexp(
                Exception, 'Timed out waiting for action to complete.'):
            wait_for_action_complete(
                fake_client, pending_action['results'][0]['action']['tag'], 0)

    def test_wait_for_action_complete_error(self):
        fake_client = FakeActionClient()
        fake_client.action['results'][0]['error'] = "id not found"
        pending_action = fake_client.enqueue_units('git/0', 'list-users', None)
        with self.assertRaisesRegexp(ValueError, 'id not found'):
            wait_for_action_complete(
                fake_client, pending_action['results'][0]['action']['tag'])

    def test_mkdir_p(self):
        d = mkdtemp()
        path = os.path.join(d, 'a/b/c')
        mkdir_p(path)
        self.assertTrue(os.path.isdir(path))
        mkdir_p(path)  # Already exists test
        rmtree(d)

    def test_get_provider_name(self):
        name = get_provider_name('ec2')
        self.assertEqual(name, 'AWS')
        name = get_provider_name('gce')
        self.assertEqual(name, 'GCE')
        name = get_provider_name('foo')
        self.assertEqual(name, 'foo')

    def test_create_bundle_yaml(self):
        bundle = create_bundle_yaml('mysql')
        self.assertEqual(bundle, get_bundle_yaml())

    def test_find_unit(self):
        status = {
            "Services": {"mongodb": {"Units": {"mongodb/0": "foo"}}}
        }
        unit = find_unit("mongodb", status)
        self.assertEqual(unit, "mongodb/0")

        status = {
            "Services": {"mongodb": {"Units": {
                "mongodb/1": "foo", "mongodb/0": "foo"}}}
        }
        unit = find_unit("mongodb", status)
        self.assertEqual(unit, "mongodb/0")

    def test_find_unit_none(self):
        status = {
            "Services": {"mongodb": {"Units": {"mongodb/1": "foo"}}}
        }
        unit = find_unit("mongodb/1", status)
        self.assertIsNone(unit, None)

        unit = find_unit("Foo", status)
        self.assertIsNone(unit, None)

    def test_get_all_test_results(self):
        temp = mkdtemp()
        files = [os.path.join(temp, 'cs:git-2015-12-02T22:22:21-result.json'),
                 os.path.join(temp, 'cs:git-2015-12-02T22:22:21-result.html'),
                 os.path.join(temp, 'cs:git-2015-12-02T22:22:22-result.json'),
                 os.path.join(temp, 'cs:foo-2015-12-02T22:22:23-result.json'),
                 os.path.join(temp, 'cs:git-2015-12-02T22:22:25-result.json')]
        index = 1
        for f in files:
            with open(f, 'w') as fp:
                fp.write(make_fake_results(date=index))
                index += 1
        results = get_all_test_results('cs:git', temp)
        self.assertEqual(len(results), 3)
        self.assertItemsEqual([r['date'] for r in results], [1, 3, 5])
        rmtree(temp)

    def test_get_benchmark_data(self):
        temp = mkdtemp()
        files = [os.path.join(temp, 'cs:git-2015-12-02T22:22:21-result.json'),
                 os.path.join(temp, 'cs:git-2015-12-02T22:22:22-result.json'),
                 os.path.join(temp, 'cs:foo-2015-12-02T22:22:23-result.json'),
                 os.path.join(temp, 'cs:git-2015-12-02T22:22:25-result.json')]
        index = 1
        for f in files:
            with open(f, 'w') as fp:
                fp.write(make_fake_results(date=index))
                index += 1
        values = get_benchmark_data('cs:git', temp, 'AWS')
        self.assertItemsEqual(values, ['100', '100', '100'])
        values = get_benchmark_data('cs:git', temp, 'Joyent')
        self.assertItemsEqual(values, ['200', '200', '200'])
        values = get_benchmark_data('cs:git', temp, 'GCE')
        self.assertItemsEqual(values, [])
        rmtree(temp)


def get_bundle_yaml():
    return """services:
    mysql:
        annotations:
            gui-x: '610'
            gui-y: '255'
        charm: mysql
        num_units: 1
"""


class FakeActionClient:

    def __init__(self):
        self.action = {}
        self.action['results'] = [{}]
        self.action['results'][0]['action'] = {'tag': 'foo'}
        self.action['results'][0]['error'] = None
        self.action['results'][0]['status'] = 'pending'

    def enqueue_units(self, unit, action, action_param):
        return self.action

    def info(self, tag):
        self.action['results'][0]['status'] = 'completed'
        self.action['results'][0]['output'] = {'users': 'user, someuser'}
        return self.action


def make_fake_results(date="2015-12-02T22:22:22", provider_name='AWS',
                      value='100', provider_name2='Joyent', value2='200'):
    return json.dumps({
        "version": 1,
        "date": date,
        "results": [
            {
                "provider_name": provider_name,
                "test_outcome": "All Pass",
                "benchmarks": [
                    {
                        "perf": {
                            "units": "ops/sec",
                            "direction": "desc",
                            "value": value
                        }
                    }
                ]
            },
            {
                "provider_name": provider_name2,
                "test_outcome": "Some Failed",
                "benchmarks": [
                    {
                        "perf": {
                            "units": "ops/sec",
                            "direction": "desc",
                            "value": value2
                        }
                    }
                ]
            },
            {
                "provider_name": 'GCE',
                "test_outcome": "Some Failed",
            }
        ],
        "bundle": {
            "services": None,
            "name": "git",
            "relations": None,
            "machines": None
        }
    })
