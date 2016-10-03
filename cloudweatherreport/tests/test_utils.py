import json
import os
from shutil import rmtree
import socket
from tempfile import (
    NamedTemporaryFile,
    mkdtemp,
)
from unittest import TestCase

from mock import call, patch
import yaml

from utils import (
    connect_juju_client,
    create_bundle_yaml,
    find_unit,
    get_all_test_results,
    get_benchmark_data,
    get_provider_name,
    is_machine_agent_started,
    iter_units,
    mkdir_p,
    read_file,
    run_action,
    wait_for_action_complete,
)
from tests.common_test import (
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
        unit = find_unit("plugin", make_fake_status())
        self.assertEqual(unit, "plugin/6")

    def test_find_unit_juju2(self):
        status = make_fake_status_juju_2()
        unit = find_unit('mysql', status)
        self.assertEqual(unit, 'mysql/0')

        unit = find_unit('wiki/0', status)
        self.assertEqual(unit, 'wiki/0')

        unit = find_unit('foo', status)
        self.assertIsNone(unit)

    def test_find_unit_none(self):
        unit = find_unit("plugin/10", make_fake_status())
        self.assertIsNone(unit, None)

        unit = find_unit("Foo", make_fake_status())
        self.assertIsNone(unit, None)

    def test_find_unit_complex(self):
        status = make_fake_status()
        unit = find_unit('plugin', status)
        self.assertEqual(unit, 'plugin/6')
        unit = find_unit('plugin/0', status)
        self.assertEqual(unit, 'plugin/6')
        unit = find_unit('plugin/1', status)
        self.assertEqual(unit, 'plugin/7')
        unit = find_unit('hive', status)
        self.assertEqual(unit, 'hive/0')
        unit = find_unit('fake', status)
        self.assertIs(unit, None)

    def test_iter_units(self):
        status = make_fake_status()
        units = list(iter_units(status))
        units = [x for x, _ in units]
        expected = ['compute-slave/10', 'compute-slave/9', 'plugin/7',
                    'hdfs-master/3', 'hive/0', 'plugin/6', 'mysql/3',
                    'secondary-namenode/3']
        self.assertItemsEqual(units, expected)

    def test_iter_units_juju2(self):
        status = make_fake_status_juju_2()
        units = list(iter_units(status))
        units = [x for x, _ in units]
        self.assertEqual(units, ['mysql/0', 'wiki/0'])

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

    def test_connect_juju_client(self):
        with patch('utils.env1', autospec=True) as jc_mock:
            jc_mock.connect.return_value = 'bar'
            env = connect_juju_client('foo', 1)
        jc_mock.connect.assert_called_once_with(env_name='foo')
        self.assertEqual(env, 'bar')

    def test_connect_juju_client_socket_timeout(self):
        with patch('utils.env2', autospec=True) as jc_mock:
            jc_mock.connect.side_effect = socket.timeout
            env = connect_juju_client('foo', 2)
        self.assertEqual(jc_mock.connect.mock_calls,
                         [call(env_name='foo'), call(env_name='foo'),
                          call(env_name='foo')])
        self.assertEqual(env, None)

    def test_is_machine_agent_started(self):
        status = {
            'EnvironmentName': 'default-joyent',
            'Services': {},
            'Networks': {},
            'Machines': {
                '0': {'HasVote': True,  'Err': None, 'InstanceId': '1234',
                      'AgentState': 'started', 'AgentSta/fiteInfo': '',
                      'Agent': {'Status': 'started'}}
            }
        }
        started = is_machine_agent_started(status, juju_major_version=1)
        self.assertEqual(started, True)

    def test_is_machine_agent_started_pending(self):
        status = {
            'EnvironmentName': 'default-joyent',
            'Services': {},
            'Networks': {},
            'Machines': {
                '0': {'HasVote': True,  'Err': None, 'InstanceId': '1234',
                      'AgentState': 'pending', 'AgentStateInfo': '',
                      'Agent': {'Status': 'pending'}}
            }
        }
        started = is_machine_agent_started(status, juju_major_version=1)
        self.assertEqual(started, False)

    def test_is_machine_agent_started_multi(self):
        status = {
            'EnvironmentName': 'default-joyent',
            'Services': {},
            'Networks': {},
            'Machines': {
                '0': {'HasVote': True,  'Err': None, 'InstanceId': '1234',
                      'AgentState': 'started', 'AgentStateInfo': '',
                      'Agent': {'Status': 'started'}},
                '1': {'HasVote': True,  'Err': None, 'InstanceId': '1234',
                      'AgentState': 'started', 'AgentStateInfo': '',
                      'Agent': {'Status': 'started'}},
            }
        }
        started = is_machine_agent_started(status, juju_major_version=1)
        self.assertEqual(started, True)

    def test_is_machine_agent_started_multi_pending(self):
        status = {
            'EnvironmentName': 'default-joyent',
            'Services': {},
            'Networks': {},
            'Machines': {
                '0': {'HasVote': True,  'Err': None, 'InstanceId': '1234',
                      'AgentState': 'started', 'AgentStateInfo': '',
                      'Agent': {'Status': 'started'}},
                '1': {'HasVote': True,  'Err': None, 'InstanceId': '1234',
                      'AgentState': 'pending', 'AgentStateInfo': '',
                      'Agent': {'Status': 'panding'}},
            }
        }
        started = is_machine_agent_started(status, juju_major_version=1)
        self.assertEqual(started, False)

    def test_is_machine_agent_started_juju2(self):
        status = make_fake_status_juju_2()
        started = is_machine_agent_started(status)
        self.assertEqual(started, True)

    def test_is_machine_agent_started_juju2_not_started(self):
        status = make_fake_status_juju_2(agent_status='pending')
        started = is_machine_agent_started(status, juju_major_version=2)
        self.assertEqual(started, False)


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


def make_fake_status_juju_2(agent_status='started'):
    return json.loads(json.dumps(
        {
            "applications": {
                "mysql": {
                    "charm": "cs:mysql-55",
                    "exposed": False,
                    "series": "trusty",
                    "units": {
                        "mysql/0": {
                            "agent-status": {
                                "status": "idle",
                            },
                            "charm": "",
                            "machine": "1",
                            "opened-ports": [
                                "3306/tcp"
                            ],
                            "public-address": "",
                            "subordinates": None,
                            "workload-status": {
                                "status": "unknown",
                            },
                            "workload-version": ""
                        }
                    },
                    "workload-version": ""
                },
                "wiki": {
                    "can-upgrade-to": "",
                    "charm": "cs:trusty/mediawiki-5",
                    "exposed": False,
                    "life": "",
                    "series": "trusty",
                    "status": {
                        "status": "unknown",
                    },
                    "units": {
                        "wiki/0": {
                            "agent-status": {
                                "status": "idle",
                                "version": "2.0-rc2"
                            },
                            "machine": "2",
                            "opened-ports": [
                                "80/tcp"
                            ],
                            "public-address": "",
                            "workload-status": {
                                "status": "unknown",
                            },
                            "workload-version": ""
                        }
                    },
                    "workload-version": ""
                }
            },
            "machines": {
                "1": {
                    "agent-status": {
                        "status": agent_status,
                        "version": "2.0-rc2"
                    },
                    "containers": {},
                    "dns-name": "127.0.0.1",
                    "hardware": "arch=amd64 cores=1",
                    "has-vote": False,
                    "id": "1",
                    "instance-id": "juju-6b8a50-1",
                    "instance-status": {
                        "status": "running",
                    },
                    "series": "trusty",
                    "wants-vote": False
                },
                "2": {
                    "agent-status": {
                        "status": "started",
                        "version": "2.0-rc2"
                    },
                    "dns-name": "127.0.0.1",
                    "hardware": "arch=amd64 cores=1",
                    "has-vote": False,
                    "id": "2",
                    "instance-id": "juju-6b8a50-2",
                    "instance-status": {
                        "status": "running",
                    },
                    "series": "trusty",
                    "wants-vote": False
                }
            },
            "model": {
                "available-version": "",
                "cloud-tag": "cloud-google",
                "name": "default",
                "region": "us-east1",
                "version": "2.0-rc2"
            },
            "relations": []
        }
    ))


def make_fake_status():
    return json.loads(json.dumps(
        {
            "AvailableVersion": "",
            "EnvironmentName": "aws",
            "Machines": {},
            "Networks": {},
            "Services": {
                "compute-slave": {
                    "Charm": "cs:trusty/apache-hadoop-compute-slave-9",
                    "Status": {
                        "Data": {},
                        "Version": ""
                    },
                    "SubordinateTo": [],
                    "Units": {
                        "compute-slave/10": {
                            "AgentState": "started",
                            "Subordinates": None,
                            "AgentStateInfo": "",
                            "Workload": {
                                "Data": {},
                                "Status": "active",
                                "Version": ""
                            }
                        },
                        "compute-slave/9": {
                            "AgentState": "started",
                            "Subordinates": {
                                "plugin/7": {
                                    "AgentState": "started",
                                    "Subordinates": None,
                                    "Workload": {
                                        "Data": {},
                                        "Version": ""
                                    }
                                }
                            },
                            "UnitAgent": {
                                "Data": {},
                                "Version": "1.25.0"
                            },
                            "Workload": {
                                "Data": {},
                                "Version": ""
                            }
                        }
                    }
                },
                "hdfs-master": {
                    "Charm": "cs:trusty/apache-hadoop-hdfs-master-9",
                    "Status": {
                        "Data": {},
                        "Version": ""
                    },
                    "SubordinateTo": [],
                    "Units": {
                        "hdfs-master/3": {
                            "AgentState": "started",
                            "Subordinates": None,
                            "Workload": {
                                "Data": {},
                                "Status": "active",
                                "Version": ""
                            }
                        }
                    }
                },
                "hive": {
                    "Charm": "cs:trusty/apache-hive-10",
                    "Status": {
                        "Data": {},
                        "Version": ""
                    },
                    "SubordinateTo": [],
                    "Units": {
                        "hive/0": {
                            "AgentState": "started",
                            "Subordinates": {
                                "plugin/6": {
                                    "AgentState": "started",
                                    "Subordinates": None,
                                    "Workload": {
                                        "Data": {},
                                        "Version": ""
                                    }
                                }
                            },
                            "Workload": {
                                "Data": {},
                                "Version": ""
                            }
                        }
                    }
                },
                "mysql": {
                    "Charm": "cs:trusty/mysql-29",
                    "Status": {
                        "Data": {},
                        "Version": ""
                    },
                    "SubordinateTo": [],
                    "Units": {
                        "mysql/3": {
                            "AgentState": "started",
                            "Subordinates": None,
                            "Workload": {
                                "Data": {},
                                "Version": ""
                            }
                        }
                    }
                },
                "plugin": {
                    "Charm": "cs:trusty/apache-hadoop-plugin-9",
                    "Status": {
                        "Data": None,
                        "Version": ""
                    },
                    "SubordinateTo": [
                        "hive",
                        "compute-slave"
                    ],
                    "Units": None
                },
                "secondary-namenode": {
                    "Charm": "cs:trusty/apache-hadoop-hdfs-secondary-7",
                    "Status": {
                        "Data": {},
                        "Version": ""
                    },
                    "SubordinateTo": [],
                    "Units": {
                        "secondary-namenode/3": {
                            "AgentState": "started",
                            "Subordinates": None,
                            "Workload": {
                                "Data": {},
                                "Version": ""
                            }
                        }
                    }
                }
            }
        }
    ))
