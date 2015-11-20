from __future__ import print_function

import argparse
from cStringIO import StringIO
import os

from bundletester import tester
from cloudweatherreport.reporter import Reporter
import jujuclient
from utils import (
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
    tester.main(args)
    return test_result.getvalue()


def run_actions(test_plan, client):
    action_results = []
    for unit, actions in test_plan['benchmark'].items():
        actions = [actions] if isinstance(actions, str) else actions
        for action in actions:
            result = run_action(client, unit, action)
            action_results.append(result)
    return action_results


def main(args):
    test_plan = None
    if args.test_plan:
        test_plan = read_file(args.test_plan, 'yaml')
    test_results = None
    action_results = None
    for env in args.controller:
        test_results = run_bundle_test(args=args, env=env, test_plan=test_plan)
        if test_plan.get('benchmark'):
            env = jujuclient.Environment.connect(env_name=env)
            client = jujuclient.Actions(env)
            action_results = run_actions(test_plan, client)
    reporter = Reporter(args, test_results, action_results)
    reporter.generate_html(args.result_output)


if __name__ == '__main__':
    args = parse_args()
    main(args)
