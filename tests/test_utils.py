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
        self.assertEqual(name, 'Amazon Web Services')
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
