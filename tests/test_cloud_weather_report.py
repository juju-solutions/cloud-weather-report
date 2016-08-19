from argparse import Namespace
from collections import namedtuple
import json
import os
from StringIO import StringIO
from datetime import datetime
from unittest import TestCase, skip

from mock import (
    call,
    MagicMock,
    patch,
)

with patch('deployer.utils.get_juju_major_version', return_value=1):
    from cloudweatherreport import cloud_weather_report, model
from . import common
from .test_utils import make_fake_status
from cloudweatherreport import utils


@skip('This is going away')
class TestCloudWeatherReport(TestCase):
    maxDiff = None

    def setUp(self):
        common.setup_test_logging(self)

    def test_parse_args_defaults(self):
        with patch('cloudweatherreport.cloud_weather_report.'
                   'get_juju_major_version',
                   autospec=True,
                   return_value=1) as gjmv_mock:
            args = cloud_weather_report.parse_args(
                ['aws', 'test_plan', '--test-id', '1234'])
        expected = Namespace(
            bundle=None, controller=['aws'], deployment=None, dryrun=False,
            exclude=None, failfast=True, juju_major_version=1,
            log_level='INFO', no_destroy=False, results_dir='results',
            skip_implicit=False, test_id='1234', test_pattern=None,
            test_plan='test_plan', testdir=os.getcwd(), tests_yaml=None,
            bucket=None, s3_creds=None, verbose=False)
        self.assertEqual(args, expected)
        gjmv_mock.assert_called_once_with()

    @patch.object(cloud_weather_report, 'get_juju_major_version')
    def test_parse_args_set_all_options(self, get_juju_major_version):
        get_juju_major_version.return_value = '3'
        args = cloud_weather_report.parse_args(
            ['aws', 'gce', 'test_plan', '--results-dir', 'results',
             '--testdir', '/test/dir', '--bundle', 'foo-bundle',
             '--deployment', 'depl', '--no-destroy', '--log-level', 'debug',
             '--dry-run', '--verbose', '--allow-failure', '--skip-implicit',
             '--exclude', 'skip_test', '--test-id', '2345', '--tests-yaml',
             'test_yaml_file', '--test-pattern', 'tp', '--bucket', 'bucket',
             '--s3-creds', 'creds.ini', '--juju-major-version', '2'])
        expected = Namespace(
            bundle='foo-bundle', controller=['aws', 'gce'], deployment='depl',
            dryrun=True, exclude=['skip_test'], failfast=False,
            juju_major_version=2, log_level='debug', no_destroy=True,
            results_dir='results', skip_implicit=True, test_id='2345',
            test_pattern='tp', test_plan='test_plan', testdir='/test/dir',
            tests_yaml='test_yaml_file', verbose=True, bucket='bucket',
            s3_creds='creds.ini')
        self.assertEqual(args, expected)

    def test_run_bundle_test(self):
        io_output = StringIO()
        test_plan = make_tst_plan()
        args = Namespace()
        with patch(
                'cloudweatherreport.cloud_weather_report.StringIO',
                autospec=True, return_value=io_output) as mock_ntf:
            with patch('cloudweatherreport.cloud_weather_report.tester.main',
                       autospec=True, side_effect=self._fake_tester_main
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
        args = Namespace(testdir=None, juju_major_version=1)
        with patch(
                'cloudweatherreport.cloud_weather_report.StringIO',
                autospec=True, return_value=io_output) as mock_ntf:
            with patch('cloudweatherreport.cloud_weather_report.tester.main',
                       autospec=True, side_effect=self._fake_tester_main
                       ) as mock_tm:
                output, status = cloud_weather_report.run_bundle_test(
                    args, 'foo', test_plan)
        self.assertEqual(output, 'test passed')
        call = Namespace(environment='foo', juju_major_version=1,
                         output=io_output, reporter='json', testdir=None,
                         tests=None)
        mock_tm.assert_called_once_with(call)
        mock_ntf.assert_called_once_with()

    def test_run_bundle_test_exception(self):
        io_output = StringIO()
        test_plan = make_tst_plan()
        args = Namespace()
        exc = 'File /path/ raise exception'
        with patch(
                'cloudweatherreport.cloud_weather_report.StringIO',
                autospec=True, return_value=io_output) as mock_ntf:
            with patch('cloudweatherreport.cloud_weather_report.tester.main',
                       autospec=True, side_effect=Exception
                       ) as mock_tm:
                with patch('traceback.format_exc', return_value=exc) as mock_f:
                    output, status = cloud_weather_report.run_bundle_test(
                        args, 'foo', test_plan)
        expected_result = utils.generate_test_result(
            'Exception (foo):\nFile /path/ raise exception')
        self.assertEqual(output, expected_result)
        self.assertEqual(status, None)
        main_call = Namespace(
            environment='foo', output=io_output, reporter='json',
            testdir='git', tests=['test1', 'test2'])
        mock_tm.assert_called_once_with(main_call)
        mock_ntf.assert_called_once_with()
        mock_f.assert_called_once_with()

    def test_run_bundle_test_provisioning_error(self):
        env = Env(agent_state='pending')
        io_output = StringIO()
        test_plan = make_tst_plan()
        args = Namespace(juju_major_version=1)
        exc = 'File /path/ raise exception'
        with patch(
                'cloudweatherreport.cloud_weather_report.StringIO',
                autospec=True, return_value=io_output) as mock_ntf:
            with patch('cloudweatherreport.cloud_weather_report.tester.main',
                       autospec=True, side_effect=Exception
                       ) as mock_tm:
                with patch('traceback.format_exc', return_value=exc) as mock_f:
                        output, status = cloud_weather_report.run_bundle_test(
                            args, 'foo', test_plan, env=env)
        expected_result = utils.generate_test_result(
            'Exception (foo):\nFile /path/ raise exception', returncode=240,
            test="Provisioning Failure")
        self.assertEqual(output, expected_result)
        self.assertEqual(status, None)
        main_call = Namespace(
            environment='foo', juju_major_version=1, output=io_output,
            reporter='json', testdir='git', tests=['test1', 'test2'])
        mock_tm.assert_called_once_with(main_call)
        mock_ntf.assert_called_once_with()
        mock_f.assert_called_once_with()

    def test_run_bundle_test_provisioning_ok(self):
        env = Env()
        io_output = StringIO()
        test_plan = make_tst_plan()
        args = Namespace(juju_major_version=1)
        exc = 'File /path/ raise exception'
        with patch(
                'cloudweatherreport.cloud_weather_report.StringIO',
                autospec=True, return_value=io_output) as mock_ntf:
            with patch('cloudweatherreport.cloud_weather_report.tester.main',
                       autospec=True, side_effect=Exception
                       ) as mock_tm:
                with patch('traceback.format_exc', return_value=exc) as mock_f:
                    output, status = cloud_weather_report.run_bundle_test(
                        args, 'foo', test_plan, env=env)
        expected_result = utils.generate_test_result(
            'Exception (foo):\nFile /path/ raise exception', returncode=1)
        self.assertEqual(output, expected_result)
        self.assertEqual(status, None)
        main_call = Namespace(
            environment='foo', juju_major_version=1, output=io_output,
            reporter='json', testdir='git', tests=['test1', 'test2'])
        mock_tm.assert_called_once_with(main_call)
        mock_ntf.assert_called_once_with()
        mock_f.assert_called_once_with()

    def test_main(self):
        status = self.make_status()
        run_bundle_test_p = patch(
            'cloudweatherreport.cloud_weather_report.run_bundle_test',
            autospec=True, return_value=(self.make_results(), status))
        juju_client_p = patch('utils.env2', autospec=True)
        with utils.temp_dir() as tempdir:
            test_plan = make_tst_plan()
            args = Namespace(controller=['aws'],
                             juju_major_version=2,
                             results_dir=tempdir,
                             bucket=None,
                             s3_creds=None,
                             test_id='1234',
                             testdir='git',
                             verbose=False)
            with run_bundle_test_p as mock_rbt:
                with juju_client_p as mock_jc:
                    mock_jc.connect.return_value.info.return_value = {
                        "ProviderType": "ec2",
                    }
                    cloud_weather_report.main(args, test_plan)
            html_filename = os.path.join(tempdir, 'git/1234/results.html')
            json_filename = os.path.join(tempdir, 'git/1234/results.json')
            assert os.path.exists(html_filename)
            assert os.path.exists(json_filename)
            with open(html_filename) as html_output:
                html_content = html_output.read()
            with open(json_filename) as json_output:
                json_content = json.loads(json_output.read())
            self.assertRegexpMatches(html_content, '<title>git</title>')
            self.assertEqual(json_content["bundle"]["name"], 'git')
            self.assertEqual(json_content["results"][0]["provider_name"],
                             'AWS')
        env = mock_jc.connect.return_value
        mock_rbt.assert_called_once_with(args=args, env_name='aws',
                                         test_plan=test_plan, env=env)

    @patch('cloudweatherreport.reporter.datetime')
    def test_main_multi_clouds(self, mdatetime):
        mdatetime.now.return_value = datetime(2016, 7, 13, 0, 0, 0)
        status = self.make_status()
        run_bundle_test_p = patch(
            'cloudweatherreport.cloud_weather_report.run_bundle_test',
            autospec=True, return_value=(self.make_results(), status))
        juju_client_p = patch('utils.env1', autospec=True)
        run_action_p = patch.object(cloud_weather_report, 'run_action',
                                    return_value=self.make_benchmark_data())
        find_unit_p = patch.object(cloud_weather_report, 'find_unit',
                                   return_value='unit/0')
        with utils.temp_dir() as tempdir:
            test_plan = make_tst_plan(benchmark=True)
            args = Namespace(controller=['aws', 'gce'],
                             juju_major_version=1,
                             results_dir=tempdir,
                             bucket=None,
                             s3_creds=None,
                             test_id='1234',
                             testdir=None,
                             verbose=False)
            with run_bundle_test_p as mock_rbt, \
                    juju_client_p as mock_jc, \
                    run_action_p as mock_ra, \
                    find_unit_p:
                (mock_jc.Environment.connect.return_value.
                 info.return_value) = {"ProviderType": "ec2"}
                cloud_weather_report.main(args, test_plan)
            json_filename = os.path.join(tempdir, 'git/1234/results.json')
            assert os.path.exists(json_filename)
            with open(json_filename) as json_output:
                json_content = json.loads(json_output.read())
        env = mock_jc.connect.return_value
        calls = [call(args=args, env_name='aws', test_plan=test_plan, env=env),
                 call(args=args, env_name='gce', test_plan=test_plan, env=env)]
        self.assertEqual(mock_rbt.mock_calls, calls)
        assert mock_ra.called
        test_data_dir = os.path.join(os.path.dirname(__file__), 'data')
        with open(os.path.join(test_data_dir, 'result-v1.json')) as fp:
            expected_data = json.load(fp)
        self.assertEqual(json_content, expected_data)

    def test_run_actions(self):
        content = """
            tests:
                - foo-test
                - bar-test
            benchmark:
                plugin:
                    terasort:
                        time: 30s
                        concurrency: 10
            """
        test_plan = model.TestPlan.from_yaml(content)
        mock_client = MagicMock()
        benchmark_data = self.make_benchmark_data()
        with patch('cloudweatherreport.cloud_weather_report.run_action',
                   autospec=True,
                   return_value=benchmark_data) as mock_cr:
            result = cloud_weather_report.run_actions(
                test_plan, MagicMock(test_id='test_id'),
                mock_client, make_fake_status())
        calls = [call(mock_client, 'plugin/6', 'terasort',
                      action_param={"time": "30s", "concurrency": 10},
                      timeout=3600)]
        self.assertEqual(mock_cr.mock_calls, calls)
        self.assertEqual(result, [
            model.BenchmarkResult(
                name='terasort',
                direction="desc",
                units="ops/sec",
                value="200",
            ),
        ])

    def test_run_actions_benchmark_with_no_param(self):
        content = """
            benchmark:
                plugin/1:
                    terasort
            """
        test_plan = model.TestPlan.from_yaml(content)
        mock_client = MagicMock()
        with patch('cloudweatherreport.cloud_weather_report.run_action',
                   autospec=True,
                   return_value=self.make_benchmark_data()) as mock_cr:
            result = cloud_weather_report.run_actions(
                test_plan, MagicMock(test_id='test_id'),
                mock_client, make_fake_status())
        calls = [call(mock_client, 'plugin/7', 'terasort', action_param=None,
                      timeout=3600)]
        self.assertEqual(mock_cr.mock_calls, calls)
        self.assertEqual(result, [
            model.BenchmarkResult(
                name='terasort',
                direction="desc",
                units="ops/sec",
                value="200",
            ),
        ])

    def test_run_actions_multi_params(self):
        content = """
            benchmark:
                plugin/0:
                    terasort:
                        time: 30s
                plugin/1:
                    terasort
            """
        test_plan = model.TestPlan.from_yaml(content)
        mock_client = MagicMock()
        with patch(
                'cloudweatherreport.cloud_weather_report.run_action',
                autospec=True,
                side_effect=[self.make_benchmark_data(),
                             self.make_benchmark_data()]) as mock_cr:
            result = cloud_weather_report.run_actions(
                test_plan, MagicMock(test_id='test_id'),
                mock_client, make_fake_status())
        calls = [call(mock_client, 'plugin/6', 'terasort',
                      action_param={"time": "30s"}, timeout=3600),
                 call(mock_client, 'plugin/7', 'terasort', action_param=None,
                      timeout=3600)]
        self.assertItemsEqual(mock_cr.mock_calls, calls)
        self.assertEqual(result, [
            model.BenchmarkResult(
                name='terasort',
                direction="desc",
                units="ops/sec",
                value="200",
            ),
            model.BenchmarkResult(
                name='terasort',
                direction="desc",
                units="ops/sec",
                value="200",
            ),
        ])

    def test_run_actions_single_and_multi_params(self):
        content = """
            benchmark:
                plugin/0:
                    terasort:
                        time: 30s
                plugin/1:
                    terasort2
            """
        test_plan = model.TestPlan.from_yaml(content)
        mock_client = MagicMock()
        with patch(
                'cloudweatherreport.cloud_weather_report.run_action',
                autospec=True,
                side_effect=[self.make_benchmark_data(),
                             self.make_benchmark_data()]) as mock_cr:
            result = cloud_weather_report.run_actions(
                test_plan, MagicMock(test_id='test_id'),
                mock_client, make_fake_status())
        calls = [call(mock_client, 'plugin/6', 'terasort',
                      action_param={"time": "30s"}, timeout=3600),
                 call(mock_client, 'plugin/7', 'terasort2',
                      action_param=None, timeout=3600)]
        self.assertItemsEqual(mock_cr.mock_calls, calls)
        self.assertItemsEqual(result, [
            model.BenchmarkResult(
                name='terasort',
                direction="desc",
                units="ops/sec",
                value="200",
            ),
            model.BenchmarkResult(
                name='terasort2',
                direction="desc",
                units="ops/sec",
                value="200",
            ),
        ])

    def _fake_tester_main(self, args):
        args.output.write('test passed'), 0

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


def make_tst_plan(multi_test_plans=False, benchmark=False):
    p = [
        {'tests': ['test1', 'test2'], 'bundle': 'git'},
        {'tests': ['test1'], 'bundle': 'mongodb'},
    ]
    if benchmark:
        p[0]['benchmark'] = {'unit/0': 'params'}
    if not multi_test_plans:
        p = p[0]
    return model.TestPlan.from_dict(p)


class Env:

    def __init__(self, agent_state='started'):
        self.agent_state = agent_state

    def status(self):
        status = {
            'EnvironmentName': 'default-joyent',
            'Services': {},
            'Networks': {},
            'Machines': {
                '0': {'HasVote': True,  'Err': None, 'InstanceId': '1234',
                      'AgentState': self.agent_state, 'AgentStateInfo': '',
                      'Agent': {'Status': self.agent_state}}
            }
        }
        return status
