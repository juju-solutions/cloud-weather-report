from datetime import (
    datetime,
    timedelta,
)
from time import sleep
import yaml


def read_file(file_path, file_type=None):
    deserializer = {'yaml': yaml.safe_load}
    with open(file_path) as stream:
        content = stream.read()
    if file_type:
        return deserializer[file_type.lower()](content)
    return content


def run_action(client, unit, action, action_param=None, timeout=300):
    pending_action = client.enqueue_units(unit, action, action_param)
    result = wait_for_action_complete(
        client, pending_action['results'][0]['action']['tag'], timeout=timeout)
    return result['results'][0].get('output')


def wait_for_action_complete(action, tag, timeout=300, pause_time=.1):
    time_limit = datetime.now() + timedelta(seconds=timeout)
    while datetime.now() < time_limit:
        result = action.info([{'Tag': tag}])
        if result['results'][0].get('error'):
            raise ValueError(result['results'][0].get('error'))
        if result['results'][0].get('status') == 'completed':
            return result
        sleep(pause_time)
    raise Exception('Timed out waiting for action to complete.')
