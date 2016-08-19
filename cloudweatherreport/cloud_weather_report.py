from __future__ import print_function

import argparse
from cStringIO import StringIO
import logging
import os
import traceback
from datetime import datetime

from bundletester import tester
import jujuclient

from cloudweatherreport.datastore import DataStore
from cloudweatherreport import model
from utils import (
    PROVISIONING_ERROR_CODE,
    configure_logging,
    connect_juju_client,
    create_bundle_yaml,
    generate_test_result,
    get_juju_major_version,
    get_juju_client_by_version,
    generate_test_id,
    find_unit,
    get_provider_name,
    is_machine_agent_started,
    run_action,
    fetch_svg,
)


def bundle_tester_args(parser):
    parser.add_argument('-t', '--testdir', default=os.getcwd())
    parser.add_argument('-b', '-c', '--bundle', type=str,
                        help='Specify a bundle a la {path/to/bundle.yaml}. '
                             'Relative paths will be mapped within the bundle '
                             'itself for remote bundles. Explicit local paths '
                             'to bundles currently not supported.'
                        )
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
    parser.add_argument('--juju-major-version', type=int,
                        default=get_juju_major_version())
    parser.add_argument('--test-id', dest="test_id", help="Test ID.",
                        default=generate_test_id())
    return parser


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('controller', nargs='+', help="Controller list.")
    parser.add_argument('test_plan', help="Test plan YAML file.")
    parser.add_argument('--results-dir', default='results',
                        help="Directory to store / find results.")
    parser.add_argument('--bucket',
                        help='Store / find results in this S3 bucket '
                             'instead of locally')
    parser.add_argument('--s3-creds',
                        help='Path to config file containing S3 credentials')
    parser = bundle_tester_args(parser)
    return parser.parse_args(argv)





def main(args, test_plan):
    log_level = logging.DEBUG if args.verbose else logging.INFO
    configure_logging(log_level)
    logging.info('Cloud Weather Report started.')

    datastore = DataStore.get(args.results_dir, args.bucket, args.s3_creds)

    args.bundle = test_plan.bundle_file
    bundle_yaml = None

    for env_name in args.controller:
        try:
            env = connect_juju_client(
                env_name, args.juju_major_version, logging=logging)
        except Exception:
            tb = traceback.format_exc()
            error = 'Jujuclient exception({}): {}'.format(env_name, tb)
            logging.error(error)
            results.append({
                "provider_name": env_name,
                "test_results": json.loads(generate_test_result(error)),
                "action_results": [],
                "info": {}})

    svg_data = fetch_svg(bundle_yaml)
    datastore.write(index.filename_json, index.as_json())
    datastore.write(index.filename_html, index.as_html())
    datastore.write(report.filename_json, report.as_json())
    datastore.write(report.filename_html, report.as_html(svg_data))
