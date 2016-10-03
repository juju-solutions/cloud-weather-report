import codecs
from contextlib import contextmanager
from datetime import (
    datetime,
    timedelta,
)
import errno
import json
import jujuclient.juju1
import jujuclient.juju2
import logging
import os
from shutil import rmtree
import socket
import subprocess
from tempfile import mkdtemp
from time import sleep
import traceback
import uuid
import yaml

from jujuclient.juju1.environment import Environment as env1
from jujuclient.juju2.environment import Environment as env2


PROVISIONING_ERROR_CODE = 240


def read_file(file_path, file_type=None):
    deserializer = {'yaml': yaml.safe_load}
    with open(file_path) as stream:
        content = stream.read()
    if file_type:
        return deserializer[file_type.lower()](content)
    return content


def run_action(client, unit, action, action_param=None, timeout=-1):
    logging.debug(
        'Action run - unit: {} action:{} param:{} timeout: {}'.format(
            unit, action, action_param, timeout))
    action_param = action_param or {}
    pending_action = client.enqueue_units(unit, action, action_param)
    if pending_action['results'][0].get('error'):
        raise Exception('Action failed {}'.format(
            pending_action['results'][0].get('error')))
    result = wait_for_action_complete(
        client, pending_action['results'][0]['action']['tag'], timeout=timeout)
    logging.debug('Action run completed. Result:\n{} '.format(result))
    return result['results'][0].get('output')


def wait_for_action_complete(action, tag, timeout=-1, pause_time=.1):
    """Wait for action to complete. Use -1 to wait indefinitely."""
    time_limit = datetime.now() + timedelta(seconds=timeout)
    not_expired = True if timeout == -1 else datetime.now() < time_limit
    result = None
    while not_expired:
        result = action.info([{'Tag': tag}])
        if result['results'][0].get('error'):
            raise ValueError(result['results'][0].get('error'))
        if result['results'][0].get('status') == 'completed':
            return result
        if result['results'][0].get('status') == 'failed':
            raise Exception('Action failed. Result: {}'.format(result))
        sleep(pause_time)
        not_expired = True if timeout == -1 else datetime.now() < time_limit
    logging.debug('Action timeout:\nAction: {} \nTag: {} \nResult: {}'.format(
        action, tag, result))
    raise Exception('Timed out waiting for action to complete.')


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def get_provider_name(provider_type):
    name = {'azure': 'Azure',
            'cloudsigma': 'CloudSigma',
            'ec2': 'AWS',
            'gce': 'GCE',
            'joyent': 'Joyent',
            'local': 'Local',
            'maas': 'MAAS',
            'openstack': 'OpenStack',
            'vsphere': 'vSphere',
            }
    try:
        return name[provider_type]
    except KeyError:
        return provider_type


def create_bundle_yaml(name=None):
    if not name:
        return None
    bundle_yaml = yaml.safe_dump({
        'services': {
            name: {
                'charm': name,
                'num_units': 1,
                'annotations': {
                    "gui-x": "610",
                    "gui-y": "255",
                },
            },
        },
    }, indent=4, default_flow_style=False)
    return bundle_yaml


def configure_logging(log_level=logging.WARNING):
    logging.basicConfig(
        level=log_level, format='%(asctime)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S')


def iter_units(status):
    applications = status.get('applications') or status.get('Services') or {}
    for app_name, app in sorted(applications.items()):
        units = app.get('units') or app.get('Units') or {}
        for unit_name, unit in sorted(units.items()):
            yield unit_name, unit
            subordinates = (unit.get('subordinates') or
                            unit.get('Subordinates') or {})
            for sub_name, sub in sorted(subordinates.items()):
                yield sub_name, sub


def find_unit(unit, status):
    unit = unit.split('/')
    name = unit[0]
    try:
        unit_index = unit[1]
    except IndexError:
        unit_index = 0
    units = [n for n, _ in iter_units(status) if n.split('/')[0] == name]
    if not units:
        return None
    try:
        return sorted(units)[int(unit_index)]
    except IndexError:
        return None


def get_all_test_results(bundle_name, dir_path):
    files = [os.path.join(dir_path, f) for f in os.listdir(dir_path)
             if f.startswith(bundle_name) and f.endswith('.json')]
    results = []
    for f in files:
        with codecs.open(f, 'r', encoding='utf-8') as fp:
            results.append(json.load(fp))
    results = sorted(results, key=lambda r: r["date"])
    return results


def get_benchmark_data(file_prefix, dir_path, provider_name):
    results = get_all_test_results(file_prefix, dir_path)
    values = []
    for result in results:
        if result.get('results'):
            for test_result in result['results']:
                if (test_result.get('benchmarks') and
                   provider_name == test_result['provider_name']):
                    try:
                        values.append(
                            test_result['benchmarks'][0].values()[0]["value"])
                    except (KeyError, AttributeError):
                        raise Exception('Non standardized benchmark format.')
    return values


def file_prefix(bundle_name):
    return "".join([c if c.isalnum() else "_" for c in bundle_name])


@contextmanager
def temp_dir(parent=None, keep=False):
    directory = mkdtemp(dir=parent)
    try:
        yield directory
    finally:
        if not keep:
            rmtree(directory)


def get_juju_major_version():
    return int(subprocess.check_output(["juju", "version"]).split(b'.')[0])


def generate_test_result(output, test='Exception', returncode=1, duration=0,
                         suite=''):
    results = {
        'tests': [
            {
                'test': test,
                'returncode': returncode,
                'duration': duration,
                'output': output,
                'suite':  suite,
            }
        ]
    }
    return json.dumps(results)


def connect_juju_client(env_name, juju_major_version, retries=3, logging=None):
    """Connect to jujuclient."""
    env = None
    juju_client = env1 if juju_major_version == 1 else env2
    for _ in xrange(retries):
        try:
            env = juju_client.connect(env_name=env_name)
            break
        except socket.timeout:
            if logging:
                tb = traceback.format_exc()
                logging.error('Jujuclient exception: {}'.format(tb))
            continue
    return env


def is_machine_agent_started(status, juju_major_version=2):
    agent_status = 'agent-status'
    status_str = 'status'
    if juju_major_version == 1:
        agent_status = 'Agent'
        status_str = 'Status'
    machines = status.get('machines') or status.get('Machines', [])
    if not machines:
        return None
    for machine in machines.values():
        if machine[agent_status][status_str] != 'started':
            return False

    return True


def generate_test_id():
    return uuid.uuid4().hex


def get_juju_client_by_version(version):
    return jujuclient.juju1 if version == 1 else jujuclient.juju2
