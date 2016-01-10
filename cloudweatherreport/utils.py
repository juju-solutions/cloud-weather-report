import codecs
from datetime import (
    datetime,
    timedelta,
)
import errno
import json
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


def find_unit(unit, env_status):
    index = re.search(r'/\d+$', unit)
    service_name = unit
    unit_index = 0
    if index:
        service_name = unit.replace(index.group(), "")
        unit_index = index.group()[1:]
    units = (env_status.get('Services') or {}).get(service_name, {}).get(
        'Units')
    if not units:
        return None
    try:
        return sorted(units.keys())[int(unit_index)]
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
