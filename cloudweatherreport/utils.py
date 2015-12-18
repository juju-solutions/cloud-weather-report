from datetime import (
    datetime,
    timedelta,
)
import errno
import logging
import os
import re
from time import sleep
import yaml


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
    while not_expired:
        result = action.info([{'Tag': tag}])
        if result['results'][0].get('error'):
            raise ValueError(result['results'][0].get('error'))
        if result['results'][0].get('status') == 'completed':
            return result
        sleep(pause_time)
        not_expired = True if timeout == -1 else datetime.now() < time_limit
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
    name = {'azure': 'Azure', 'cloudsigma': 'CloudSigma',
            'ec2': 'Amazon Web Services', 'gce': 'Google Compute Engine',
            'joyent': 'Joyent', 'local': 'Local', 'maas': 'MAAS',
            'openstack': 'OpenStack', 'vsphere': 'vSphere',
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


def find_unit_by_service_name(service_name, env_status):
    units = (env_status.get('Services') or {}).get(service_name, {}).get(
        'Units')
    if not units:
        return None
    unit = sorted(units.keys())[0]
    return unit


def is_unit(unit):
    r = re.search(r'/\d+$', unit)
    if r:
        return True
    return False
