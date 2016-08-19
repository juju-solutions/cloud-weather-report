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
import requests

import jujuclient.juju1.environment
import jujuclient.juju2.environment
import jujuclient.juju1.facades
import jujuclient.juju2.facades


PROVISIONING_ERROR_CODE = 240

ISO_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def get_bundle_yaml(status):
    if not status:
        return None
    if status.bundle_yaml:
        return status.bundle_yaml
    elif status.charm:
        return create_bundle_yaml(status.charm.get("name"))
    return None


def serializer(obj):
    """
    Fall-back serializer.

    Currently only handles datetime objects.
    """
    if isinstance(obj, datetime):
        return obj.strftime(ISO_TIME_FORMAT)
    else:
        raise TypeError('%s is not serializable' % obj)


def fetch_svg(bundle_yaml):
    if not bundle_yaml:
        return None
    try:
        r = requests.post('http://svg.juju.solutions', bundle_yaml)
    except Exception:
        logging.warn("Timeout exception from svg.juju.solution "
                     "for \nbundle.yaml:\n{}".format(bundle_yaml),)
        return None
    if r.status_code != requests.codes.ok:
        logging.warn("Could not generate svg. Response from "
                     "svg.juju.solutions: \n"
                     "Status code:{} \nContent: {}\n"
                     "bundle.yaml:\n{}".format(r.status_code, r.content,
                                               bundle_yaml))
        return None
    return r.content


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


@contextmanager
def temp_dir(parent=None, keep=False):
    directory = mkdtemp(dir=parent)
    try:
        yield directory
    finally:
        if not keep:
            rmtree(directory)


@contextmanager
def chdir(path):
    orig = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(orig)


def get_juju_major_version():
    return int(subprocess.check_output(["juju", "version"]).split(b'.')[0])


def get_versioned_juju_api(version=None):
    if version is None:
        version = get_juju_major_version()
    return jujuclient.juju1 if version == 1 else jujuclient.juju2


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


def connect_juju_client(env_name, juju_major_version=None, retries=3,
                        logging=None):
    """Connect to jujuclient."""
    env = None
    juju_client = get_versioned_juju_api().environment.Environment
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


def humanize_date(value, input_format=ISO_TIME_FORMAT):
    if isinstance(value, basestring):
        value = datetime.strptime(value, input_format)
    return value.strftime("%b %d, %Y at %H:%M")
