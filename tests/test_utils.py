from tempfile import NamedTemporaryFile
from unittest import TestCase

import yaml

from cloudweatherreport.utils import (
    read_file,
    run_action,
    wait_for_action_complete,
)


class TestUtil(TestCase):

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
