from argparse import Namespace
from collections import namedtuple
import json
import os
from shutil import rmtree
from StringIO import StringIO
from tempfile import (
    NamedTemporaryFile,
    mkdtemp,
)
from unittest import TestCase

from mock import (
    call,
    MagicMock,
    patch,
)
import yaml

from cloudweatherreport import cloud_weather_report
from tests.common_test import setup_test_logging


class TestCloudWeatherReport(TestCase):

    def setUp(self):
        setup_test_logging(self)

    def test_parse_args_defaults(self):
        args = cloud_weather_report.parse_args(['aws', 'test_plan'])
        expected = Namespace(
            bundle=None, controller=['aws'], deployment=None, dryrun=False,
            exclude=None, failfast=True, log_level='INFO',
            no_destroy=False, result_output='result.html',
            skip_implicit=False, test_pattern=None, test_plan='test_plan',
            testdir=os.getcwd(), tests_yaml=None, verbose=False)
        self.assertEqual(args, expected)

    def test_parse_args_set_all_options(self):
        args = cloud_weather_report.parse_args(
            ['aws', 'gce', 'test_plan', '--result-output', 'result',
             '--testdir', '/test/dir', '--bundle', 'foo-bundle',
             '--deployment', 'depl', '--no-destroy', '--log-level', 'debug',
             '--dry-run', '--verbose', '--allow-failure', '--skip-implicit',
             '--exclude', 'skip_test', '--tests-yaml', 'test_yaml_file',
             '--test-pattern', 'tp'])
        expected = Namespace(
            bundle='foo-bundle', controller=['aws', 'gce'], deployment='depl',
            dryrun=True, exclude=['skip_test'], failfast=False,
            log_level='debug', no_destroy=True, result_output='result',
            skip_implicit=True, test_pattern='tp', test_plan='test_plan',
            testdir='/test/dir', tests_yaml='test_yaml_file', verbose=True)
        self.assertEqual(args, expected)

    def test_run_bundle_test(self):
        io_output = StringIO()
        test_plan = self.make_tst_plan()
        args = Namespace()
        with patch(
                'cloudweatherreport.cloud_weather_report.StringIO',
                autospec=True, return_value=io_output) as mock_ntf:
            with patch('cloudweatherreport.cloud_weather_report.tester.main',
                       autospec=True, side_effect=self.fake_tester_main
                       ) as mock_tm:
                output, status = cloud_weather_report.run_bundle_test(
                    args, 'foo', test_plan)
        self.assertEqual(output, 'test passed')
        call = Namespace(environment='foo', output=io_output, reporter='json',
                         testdir='git', tests=['test1', 'test2'])
        mock_tm.assert_called_once_with(call)
        mock_ntf.assert_called_once_with()

    def test_run_bundle_test_no_test_plan(self):
        io_output = StringIO()
        test_plan = None
        args = Namespace(testdir=None)
        with patch(
                'cloudweatherreport.cloud_weather_report.StringIO',
                autospec=True, return_value=io_output) as mock_ntf:
            with patch('cloudweatherreport.cloud_weather_report.tester.main',
                       autospec=True, side_effect=self.fake_tester_main
                       ) as mock_tm:
                output, status = cloud_weather_report.run_bundle_test(
                    args, 'foo', test_plan)
        self.assertEqual(output, 'test passed')
        call = Namespace(environment='foo', output=io_output, reporter='json',
                         testdir=None, tests=None)
        mock_tm.assert_called_once_with(call)
        mock_ntf.assert_called_once_with()

    def test_main(self):
        status = self.make_status()
        run_bundle_test_p = patch(
            'cloudweatherreport.cloud_weather_report.run_bundle_test',
            autospec=True, return_value=(self.make_results(), status))
        juju_client_p = patch(
            'cloudweatherreport.cloud_weather_report.jujuclient',
            autospec=True)
        with NamedTemporaryFile() as html_output:
            with NamedTemporaryFile() as json_output:
                with NamedTemporaryFile() as test_plan_file:
                    test_plan = self.make_tst_plan_file(test_plan_file.name)
                    args = Namespace(controller=['aws'],
                                     result_output=html_output.name,
                                     test_plan=test_plan_file.name,
                                     testdir='git',
                                     verbose=False)
                    get_filenames_p = patch(
                        'cloudweatherreport.cloud_weather_report.'
                        'get_filenames', autospec=True, return_value=(
                            html_output.name, json_output.name))
                    with run_bundle_test_p as mock_rbt:
                        with get_filenames_p as mock_gf:
                            with juju_client_p as mock_jc:
                                (mock_jc.Environment.connect.return_value.
                                 info.return_value) = {"ProviderType": "ec2"}
                                cloud_weather_report.main(args)
                html_content = html_output.read()
                json_content = json.loads(json_output.read())
            self.assertRegexpMatches(html_content, '<title>git</title>')
            self.assertEqual(json_content["bundle"]["name"], 'git')
            self.assertEqual(json_content["results"][0]["provider_name"],
                             'AWS')
        mock_rbt.assert_called_once_with(args=args, env='aws',
                                         test_plan=test_plan)
        mock_gf.assert_called_once_with('git')

    def test_main_multi_clouds(self):
        status = self.make_status()
        run_bundle_test_p = patch(
            'cloudweatherreport.cloud_weather_report.run_bundle_test',
            autospec=True, return_value=(self.make_results(), status))
        juju_client_p = patch(
            'cloudweatherreport.cloud_weather_report.jujuclient',
            autospec=True)
        with NamedTemporaryFile() as test_plan_file:
            with NamedTemporaryFile() as html_output:
                with NamedTemporaryFile() as json_output:
                    test_plan = self.make_tst_plan_file(test_plan_file.name)
                    args = Namespace(controller=['aws', 'gce'],
                                     result_output="result.html",
                                     test_plan=test_plan_file.name,
                                     testdir=None,
                                     verbose=False)
                    get_filenames_p = patch(
                        'cloudweatherreport.cloud_weather_report.'
                        'get_filenames', autospec=True, return_value=(
                            html_output.name, json_output.name))
                    with run_bundle_test_p as mock_rbt:
                        with get_filenames_p as mock_gf:
                            with juju_client_p as mock_jc:
                                (mock_jc.Environment.connect.return_value.
                                 info.return_value) = {"ProviderType": "ec2"}
                                cloud_weather_report.main(args)
                    json_content = json.loads(json_output.read())
        calls = [call(args=args, env='aws', test_plan=test_plan),
                 call(args=args, env='gce', test_plan=test_plan)]
        self.assertEqual(mock_rbt.mock_calls, calls)
        mock_gf.assert_called_once_with('git')
        self.assertEqual(json_content["bundle"]["name"], 'git')

    def test_run_actions(self):
        content = """
            tests:
                - foo-test
                - bar-test
            benchmark:
                siege/0:
                    siege:
                        time: 30s
                        concurrency: 10
            """
        test_plan = yaml.load(content)
        mock_client = MagicMock()
        with patch('cloudweatherreport.cloud_weather_report.run_action',
                   autospec=True,
                   return_value=self.make_benchmark_data()) as mock_cr:
            result = cloud_weather_report.run_actions(
                test_plan, mock_client, self.make_env_status())
        calls = [call(mock_client, 'siege/0', 'siege',
                      action_param={"time": "30s", "concurrency": 10})]
        self.assertEqual(mock_cr.mock_calls, calls)
        self.assertEqual(result, [
            {"siege": self.make_benchmark_data()["meta"]["composite"]}])

    def test_run_actions_benchmark_with_no_param(self):
        content = """
            benchmark:
                siege/0:
                    siege
            """
        test_plan = yaml.load(content)
        mock_client = MagicMock()
        with patch('cloudweatherreport.cloud_weather_report.run_action',
                   autospec=True,
                   return_value=self.make_benchmark_data()) as mock_cr:
            result = cloud_weather_report.run_actions(
                test_plan, mock_client, self.make_env_status())
        calls = [call(mock_client, 'siege/0', 'siege', action_param=None)]
        self.assertEqual(mock_cr.mock_calls, calls)
        self.assertEqual(result, [
            {"siege": self.make_benchmark_data()["meta"]["composite"]}])

    def test_run_actions_multi_params(self):
        content = """
            benchmark:
                siege/0:
                    siege:
                        time: 30s
                        concurrency: 10
                mongodb/0:
                    perf:
                        runtime: 60
            """
        test_plan = yaml.load(content)
        mock_client = MagicMock()
        with patch(
                'cloudweatherreport.cloud_weather_report.run_action',
                autospec=True,
                side_effect=[self.make_benchmark_data(),
                             self.make_benchmark_data()]) as mock_cr:
            result = cloud_weather_report.run_actions(
                test_plan, mock_client, self.make_env_status())
        calls = [call(mock_client, 'siege/0', 'siege',
                      action_param={"time": "30s", "concurrency": 10}),
                 call(mock_client, 'mongodb/0', 'perf',
                      action_param={"runtime": 60})]
        self.assertItemsEqual(mock_cr.mock_calls, calls)
        self.assertEqual(result, [
            {'perf': self.make_benchmark_data()["meta"]["composite"]},
            {'siege': self.make_benchmark_data()["meta"]["composite"]}])

    def test_run_actions_single_and_multi_params(self):
        content = """
            benchmark:
                siege/0:
                    siege:
                        time: 30s
                        concurrency: 10
                mongodb:
                    perf
            """
        test_plan = yaml.load(content)
        mock_client = MagicMock()
        with patch(
                'cloudweatherreport.cloud_weather_report.run_action',
                autospec=True,
                side_effect=[self.make_benchmark_data(),
                             self.make_benchmark_data()]) as mock_cr:
            result = cloud_weather_report.run_actions(
                test_plan, mock_client, self.make_env_status())
        calls = [call(mock_client, 'siege/0', 'siege',
                      action_param={"time": "30s", "concurrency": 10}),
                 call(mock_client, 'mongodb/0', 'perf',
                      action_param=None)]
        self.assertItemsEqual(mock_cr.mock_calls, calls)
        self.assertEqual(result, [
            {"perf": self.make_benchmark_data()["meta"]["composite"]},
            {"siege": self.make_benchmark_data()["meta"]["composite"]}])

    def test_get_filenames(self):
        tempdir = mkdtemp()
        h_file, j_file = cloud_weather_report.get_filenames('git')
        rmtree(tempdir)
        self.assertTrue(h_file.startswith('results/git-') and
                        h_file.endswith('.html'))
        self.assertTrue(j_file.startswith('results/git-') and
                        j_file.endswith('.json'))

    def test_get_filenames_url(self):
        tempdir = mkdtemp()
        h_file, j_file = cloud_weather_report.get_filenames(
            'http://example.com/~git')
        rmtree(tempdir)
        self.assertTrue(h_file.startswith(
            'results/http___example_com__git') and h_file.endswith('.html'))
        self.assertTrue(j_file.startswith(
            'results/http___example_com__git') and j_file.endswith('.json'))
        h_file, j_file = cloud_weather_report.get_filenames(
            'cs:~user/mysql-benchmark')
        self.assertTrue(j_file.startswith(
            'results/cs__user_mysql_benchmark') and j_file.endswith('.json'))

    def fake_tester_main(self, args):
        args.output.write('test passed'), 0

    def make_tst_plan_file(self, filename):
        test_plan = self.make_tst_plan()
        content = yaml.dump(test_plan)
        with open(filename, 'w') as yaml_file:
            yaml_file.write(content)
        return yaml.load(content)

    def make_tst_plan(self):
        return {'tests': ['test1', 'test2'], 'bundle': 'git'}

    def make_results(self):
        return json.dumps(
            {
                'tests': [
                    {'returncode': 0,
                     'test': 'charm-proof',
                     'output': 'foo',
                     'duration': 1.55,
                     'suite': 'git',
                     },
                    {'returncode': 0,
                     'test': '00-setup',
                     'output': 'foo',
                     'duration': 2.55,
                     'suite': 'git'},
                    {'returncode': 1,
                     'test': '10-actions',
                     'output': 'foo',
                     'duration': 3.55,
                     'suite': 'git',
                     }
                ],
            })

    def make_status(self):
        status = namedtuple('status', ['bundle_yaml', 'charm' 'return_code'])
        status.return_code = 0
        status.bundle_yaml = None
        status.charm = None
        return status

    def make_benchmark_data(self):
        return {
            "meta": {
                "composite": {
                    "direction": "desc",
                    "units": "ops/sec",
                    "value": "200"
                }
            }
        }

    def make_env_status(self):
        return {
            "Services": {
                "siege": {"Units": {"siege/0": "foo"}},
                "mongodb": {"Units": {"mongodb/0": "foo"}}}
        }
