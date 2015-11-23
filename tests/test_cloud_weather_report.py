from argparse import Namespace
import os
from StringIO import StringIO
from tempfile import NamedTemporaryFile
from unittest import TestCase

from mock import (
    call,
    MagicMock,
    patch,
)
import yaml

from cloudweatherreport import cloud_weather_report


class TestCloudWeatherReport(TestCase):

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
                output = cloud_weather_report.run_bundle_test(
                    args, 'foo', test_plan)
        self.assertEqual(output, 'test passed')
        call = Namespace(environment='foo', output=io_output, reporter='json',
                         testdir='bundle-url', tests=['test1', 'test2'])
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
                output = cloud_weather_report.run_bundle_test(
                    args, 'foo', test_plan)
        self.assertEqual(output, 'test passed')
        call = Namespace(environment='foo', output=io_output, reporter='json',
                         testdir=None, tests=None)
        mock_tm.assert_called_once_with(call)
        mock_ntf.assert_called_once_with()

    def test_main(self):
        with NamedTemporaryFile() as output:
            with NamedTemporaryFile() as test_plan_file:
                test_plan = self.make_tst_plan_file(test_plan_file.name)
                args = Namespace(controller=['aws'],
                                 result_output=output.name,
                                 test_plan=test_plan_file.name,
                                 testdir='git')
                with patch('cloudweatherreport.cloud_weather_report.'
                           'run_bundle_test',
                           autospec=True) as mock_rbt:
                    cloud_weather_report.main(args)
            html_output = output.read()
            self.assertEqual(html_output, self.get_html_code())
        mock_rbt.assert_called_once_with(args=args, env='aws',
                                         test_plan=test_plan)

    def test_main_multi_clouds(self):
        with NamedTemporaryFile() as test_plan_file:
            test_plan = self.make_tst_plan_file(test_plan_file.name)
            args = Namespace(controller=['aws', 'gce'],
                             result_output="result.html",
                             test_plan=test_plan_file.name,
                             testdir=None)
            with patch('cloudweatherreport.cloud_weather_report.'
                       'run_bundle_test',
                       autospec=True) as mock_rbt:
                cloud_weather_report.main(args)
        calls = [call(args=args, env='aws', test_plan=test_plan),
                 call(args=args, env='gce', test_plan=test_plan)]
        self.assertEqual(mock_rbt.mock_calls, calls)

    def test_run_actions(self):
        content = """
            tests:
                - foo-test
                - bar-test
            benchmark:
                unit_1:
                    - action1
                    - action2
                unit_2: action
            """
        test_plan = yaml.load(content)
        mock_client = MagicMock()
        with patch('cloudweatherreport.cloud_weather_report.run_action',
                   autospec=True, side_effect=[3, 2, 1]) as mock_cr:
            result = cloud_weather_report.run_actions(test_plan, mock_client)
        calls = [call(mock_client, 'unit_1', 'action1'),
                 call(mock_client, 'unit_1', 'action2'),
                 call(mock_client, 'unit_2', 'action')]
        self.assertEqual(mock_cr.mock_calls, calls)
        self.assertEqual(result, [3, 2, 1])

    def fake_tester_main(self, args):
        args.output.write('test passed')

    def make_tst_plan_file(self, filename):
        test_plan = self.make_tst_plan()
        content = yaml.dump(test_plan)
        with open(filename, 'w') as yaml_file:
            yaml_file.write(content)
        return yaml.load(content)

    def make_tst_plan(self):
        return {'tests': ['test1', 'test2'], 'bundle': 'bundle-url'}

    def get_html_code(self):
        return ('<!DOCTYPE html>\n<html lang="en">\n<head>\n    '
                '<meta charset="UTF-8">\n    <title>git</title>\n</head>\n'
                '<body>\n\n</body>\n</html>')
