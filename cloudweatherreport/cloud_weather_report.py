from __future__ import print_function

import argparse
from cStringIO import StringIO
from datetime import datetime
import json
import logging
import os
import subprocess
import sys

from bundletester import tester
import jujuclient

from cloudweatherreport.reporter import Reporter
from utils import (
    configure_logging,
    create_bundle_yaml,
    get_benchmark_data,
    file_prefix,
    find_unit,
    get_provider_name,
    mkdir_p,
    read_file,
    run_action,
)


def bundle_tester_args(parser):
    parser.add_argument('-t', '--testdir', default=os.getcwd())
    parser.add_argument('-b', '-c', '--bundle',
                        type=str,
                        help=("""
                        Specify a bundle ala
                        {path/to/bundle.yaml}. Relative paths will be
                        mapped within the bundle itself for remote
                        bundles. Explicit local paths to bundles
                        currently not supported.
                        """))
    parser.add_argument('-d', '--deployment')
    parser.add_argument('--no-destroy', action="store_true")
    parser.add_argument('-l', '--log-level', dest="log_level",
                        default='INFO')
    parser.add_argument('-n', '--dry-run', action="store_true",
                        dest="dryrun")
    parser.add_argument('-v', '--verbose', action="store_true")
    parser.add_argument('-F', '--allow-failure', dest="failfast",
                        action="store_false")
    parser.add_argument('-s', '--skip-implicit', action="store_true",
                        help="Don't include automatically generated tests")
    parser.add_argument('-x', '--exclude', dest="exclude", action="append")
    parser.add_argument('-y', '--tests-yaml', dest="tests_yaml",
                        help="Path to a tests.yaml file which will "
                        "override the one in the charm or bundle "
                        "being tested.")
    parser.add_argument('--test-pattern', dest="test_pattern")
    return parser


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('controller', nargs='+', help="Controller list.")
    parser.add_argument('test_plan', help="Test plan YAML file.")
    parser.add_argument('--result-output', help="Test result output file.",
                        default='result.html')
    parser = bundle_tester_args(parser)
    return parser.parse_args(argv)


def run_bundle_test(args, env, test_plan=None):
    test_result = StringIO()
    args.output = test_result
    args.tests = test_plan.get('tests') if test_plan else None
    args.environment = env
    args.reporter = 'json'
    args.testdir = test_plan.get('bundle') if test_plan else args.testdir
    status = tester.main(args)
    return test_result.getvalue(), status


def run_actions(test_plan, client, env_status, bundle_name=None):
    action_results = []
    for unit, actions in test_plan['benchmark'].items():
        actions = {actions: None} if isinstance(actions, str) else actions
        for action, params in actions.items():
            logging.info('Running benchmark - Unit: {} Name: {} Params: {}'.
                         format(unit, action, params))
            real_unit = find_unit(unit, env_status)
            if not real_unit:
                raise Exception("unit not found: {}".format(unit))
            result = run_action(client, real_unit, action, action_param=params)
            composite = result.get('meta', {}).get('composite')
            if composite:
                action_results.append({action: composite})
            logging.info('Benchmark completed.')
    return action_results


def get_filenames(bundle):
    prefix = file_prefix(bundle)
    now = datetime.now().replace(microsecond=0).isoformat()
    html_filename = "{}-{}-result.html".format(prefix, now)
    json_filename = "{}-{}-result.json".format(prefix, now)
    result_dir = 'results'
    mkdir_p(result_dir)
    html_filename = os.path.join(result_dir, html_filename)
    json_filename = os.path.join(result_dir, json_filename)
    return html_filename, json_filename


def get_bundle_yaml(status):
    if not status:
        return None
    if status.bundle_yaml:
        return status.bundle_yaml
    elif status.charm:
        return create_bundle_yaml(status.charm.get("name"))
    return None


def main(args):
    log_level = logging.DEBUG if args.verbose else logging.INFO
    configure_logging(log_level)
    logging.info('Cloud Weather Report started.')
    test_plan = None
    if args.test_plan:
        test_plan = read_file(args.test_plan, 'yaml')
    results = []
    status = None
    bundle = test_plan.get('bundle')
    html_filename, json_filename = get_filenames(bundle)
    for env_name in args.controller:
        env = jujuclient.Environment.connect(env_name=env_name)
        env_info = env.info()
        provider_name = get_provider_name(env_info["ProviderType"])
        logging.info('Running test on {}.'.format(provider_name))
        test_results, status = run_bundle_test(
            args=args, env=env_name, test_plan=test_plan)
        client = jujuclient.Actions(env)
        action_results = []
        if test_plan.get('benchmark'):
            action_results = run_actions(test_plan, client, env.status())
            all_values = get_benchmark_data(
                file_prefix(bundle), os.path.dirname(json_filename),
                provider_name)
            value = action_results[0].values()[0]['value']
            action_results[0].values()[0]['all_values'] = all_values + [value]
        results.append({
            "provider_name": provider_name,
            "test_results": json.loads(test_results) if test_results else None,
            "action_results": action_results,
            "info": env_info})
    bundle_yaml = get_bundle_yaml(status)
    reporter = Reporter(bundle=bundle, results=results, options=args,
                        bundle_yaml=bundle_yaml)
    reporter.generate(html_filename=html_filename, json_filename=json_filename)
    return html_filename


def file_open_with_app(filename):
    opener = {'linux2': 'xdg-open', 'linux': 'xdg-open', 'darwin': 'open',
              'win32': 'start'}
    try:
        subprocess.call([opener[sys.platform], filename])
    except:
        pass


if __name__ == '__main__':
    args = parse_args()
    html_filename = main(args)
    print("Test result:\n  {}".format(html_filename))
    file_open_with_app(html_filename)
