from __future__ import print_function

import multiprocessing as mp
import argparse
from cStringIO import StringIO
from datetime import datetime
import logging
import os
import traceback
from copy import copy
from pkg_resources import resource_string

from bundletester import tester

from cloudweatherreport import model
from cloudweatherreport.datastore import DataStore
from cloudweatherreport.utils import (
    configure_logging,
    connect_juju_client,
    find_unit,
    fetch_svg,
    get_provider_name,
    run_action,
    get_bundle_yaml,
    get_juju_major_version,
    get_versioned_juju_api,
    generate_test_id,
    temp_tmpdir,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('controllers', nargs='+', help="Controller list.")
    parser.add_argument('test_plan', help="Test plan YAML file.")
    parser.add_argument('--results-dir', default='results',
                        help="Directory to store / find results.")
    parser.add_argument('--bucket',
                        help='Store / find results in this S3 bucket '
                             'instead of locally')
    parser.add_argument('--s3-creds',
                        help='Path to config file containing S3 credentials')
    parser.add_argument('--s3-private', dest='s3_public',
                        action='store_false', default=True,
                        help='Do not make the files written to S3 public-read')
    parser.add_argument('--results-per-bundle', default=40, type=int,
                        help='Maximum number of results to list per bundle in '
                             'the index.  Older results will not be listed, '
                             'but the result reports themselves will be '
                             'preserved.')

    # bundle tester args
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
                        choices=['DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL',
                                 'FATAL'], default='INFO')
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
    parser.add_argument('--test-id', dest="test_id", help="Test ID.",
                        default=generate_test_id())
    options = parser.parse_args(argv)
    options.juju_major_version = get_juju_major_version()
    configure_logging(getattr(logging, options.log_level))
    return options


class Runner(mp.Process):
    def __init__(self, controller, cli_args, *args, **kwargs):
        super(Runner, self).__init__(*args, **kwargs)
        self.controller = controller
        self.args = copy(cli_args)
        self.test_id = self.args.test_id

    def run(self):
        test_plans = model.TestPlan.load_plans(self.args.test_plan)
        for test_plan in test_plans:
            self.run_plan(test_plan)

    def load_index(self, datastore):
        index_filename = model.ReportIndex.full_index_filename_json
        if datastore.exists(index_filename):
            index_json = datastore.read(index_filename)
            return model.ReportIndex.from_json(index_json)
        else:
            return model.ReportIndex()

    def load_report(self, datastore, index, test_plan):
        filename = test_plan.report_filename(self.test_id)
        old_filename = test_plan.old_report_filename(self.test_id)
        if datastore.exists(filename):
            report = model.Report.from_json(datastore.read(filename))
        elif datastore.exists(old_filename):
            report = model.Report.from_json(datastore.read(old_filename))
        else:
            report = model.Report(
                version=2,
                test_id=self.test_id,
                date=datetime.now(),
                bundle=model.BundleInfo(
                    ref=test_plan.bundle,
                    name=test_plan.bundle_name,
                    url=test_plan.url),
            )
            prev_report = index.find_previous_report(report)
            if prev_report:
                prev_file = prev_report.filename_json
                prev_report_json = datastore.read(prev_file)
                prev_report = model.Report.from_json(prev_report_json)
                report.upsert_benchmarks(prev_report.benchmarks)
        return report

    def run_plan(self, test_plan):
        env = connect_juju_client(self.controller, logging=logging)
        if not env:
            logging.error("Jujuclient could not connect to {} ".format(
                self.controller))
            return False
        env.name = self.controller
        provider = (env.info().get("provider-type") or
                    env.info().get("ProviderType"))
        env.provider_name = get_provider_name(provider)
        logging.info('Running test on {}.'.format(env.provider_name))
        try:
            test_result = self.run_tests(test_plan, env)
            benchmark_results = self.run_benchmarks(test_plan, env)
        except Exception:
            tb = traceback.format_exc()
            error = "Exception ({}):\n{}".format(env.name, tb)
            logging.error(error)
            # create a fake SuiteResult to hold exception traceback
            test_result = model.SuiteResult(
                provider=env.provider_name,
                test_outcome='Error Running Tests',
                tests=[model.TestResult(
                    name='Error Running Tests',
                    duration=0.0,
                    output=error,
                    result='INFRA',
                )])
            return False

        datastore = DataStore.get(
            self.args.results_dir,
            self.args.bucket,
            self.args.s3_creds,
            self.args.s3_public)
        svg_data = fetch_svg(test_result.bundle_yaml)
        with datastore.lock():
            index = self.load_index(datastore)
            report = self.load_report(datastore, index, test_plan)
            report.upsert_result(test_result)
            report.upsert_benchmarks(benchmark_results)
            index.upsert_report(report)
            datastore.write(
                'css/base.css',
                resource_string(__name__,
                                'static/css/base.css').decode('utf8'))
            datastore.write(
                'css/vanilla.min.css',
                resource_string(__name__,
                                'static/css/vanilla.min.css').decode('utf8'))
            datastore.write(index.full_index_filename_json, index.as_json())
            datastore.write(index.full_index_filename_html, index.as_html())
            datastore.write(report.filename_json, report.as_json())
            datastore.write(report.filename_html, report.as_html(svg_data))
            datastore.write(report.filename_xml, report.as_xml())
            datastore.write(index.summary_filename_html, index.summary_html())
            datastore.write(index.summary_filename_json, index.summary_json())
            for bundle_name in index.bundle_names():
                datastore.write(
                    index.bundle_index_html(bundle_name),
                    index.as_html(bundle_name,
                                  limit=self.args.results_per_bundle))
                datastore.write(
                    index.bundle_index_json(bundle_name),
                    index.as_json(bundle_name,
                                  limit=self.args.results_per_bundle))
        return True

    def run_tests(self, test_plan, env):
        """
        Run BundleTester and create or update the report accordingly.

        :return: True if the test environment was provisioned and deployed
        """
        env_name = env.name
        bundletester_output = StringIO()
        self.args.output = bundletester_output
        self.args.tests = test_plan.tests if test_plan else None
        self.args.environment = env_name
        self.args.reporter = 'json'
        self.args.testdir = test_plan.bundle
        if test_plan.bundle_file:
            self.args.bundle = test_plan.bundle_file
        status = tester.main(self.args)
        result = model.SuiteResult.from_bundletester_output(
            env.provider_name,
            bundletester_output.getvalue())
        result.bundle_yaml = get_bundle_yaml(status)
        return result

    def run_benchmarks(self, test_plan, env):
        actions_client = get_versioned_juju_api().facades.Actions(env)
        env_status = env.status()
        benchmarks = []
        for benchmark_plan in test_plan.benchmarks:
            logging.info('Running benchmark {} on {} with params: {}'.format(
                benchmark_plan.action,
                benchmark_plan.unit,
                benchmark_plan.params))
            real_unit = find_unit(benchmark_plan.unit, env_status)
            if not real_unit:
                logging.error("unit not found: {}".format(benchmark_plan.unit))
                continue
            try:
                result = run_action(
                    actions_client,
                    real_unit,
                    benchmark_plan.action,
                    action_param=benchmark_plan.params,
                    timeout=3600)
            except Exception as e:
                logging.error('Action run failed: {}'.format(str(e)))
                continue
            composite = result.get('meta', {}).get('composite')
            if not composite:
                logging.error('Skipping benchmark missing composite key: '
                              '{}'.format(benchmark_plan.action))
                continue
            composite.update({
                'name': benchmark_plan.action,
                'test_id': self.test_id,
                'provider': env.provider_name,
            })
            benchmarks.append(model.Benchmark.from_action(composite))
            logging.info('Benchmark completed.')
        return benchmarks


def entry_point():
    args = parse_args()
    processes = []
    with temp_tmpdir():
        if len(args.controllers) > 1:
            for controller in args.controllers:
                processes.append(Runner(controller, args))
                processes[-1].start()
            for p in processes:
                p.join()
        else:
            Runner(args.controllers[0], args).run()


if __name__ == '__main__':
    entry_point()
