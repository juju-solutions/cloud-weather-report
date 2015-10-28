from argparse import Namespace
import os
from StringIO import StringIO
from unittest import TestCase

from mock import (
    patch,
    call,
)

from cloudweatherreport import cloud_weather_report


class TestRunner(TestCase):

    def test_parse_args_defaults(self):
        args = cloud_weather_report.parse_args(['aws', 'test_plan'])
        expected = Namespace(
            bundle=None, controller=['aws'], deployment=None, dryrun=False,
            exclude=None, failfast=True, log_level='INFO',
            no_destroy=False, result_output=None,
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
        args = Namespace()
        io_output = StringIO()
        with patch(
                'cloudweatherreport.cloud_weather_report.StringIO',
                autospec=True, return_value=io_output) as mock_ntf:
            with patch('cloudweatherreport.cloud_weather_report.tester.main',
                       autospec=True, side_effect=self.fake_tester_main
                       ) as mock_tm:
                output = cloud_weather_report.run_bundle_test(args, 'foo')
        self.assertEqual(output, 'test passed')
        call = Namespace(environment='foo', output=io_output, reporter='json',
                         tests=None)
        mock_tm.assert_called_once_with(call)
        mock_ntf.assert_called_once_with()

    def fake_tester_main(self, args):
        args.output.write('test passed')

    def test_main(self):
        args = Namespace(controller=['aws'])
        with patch('cloudweatherreport.cloud_weather_report.run_bundle_test',
                   autospec=True) as mock_rbt:
            cloud_weather_report.main(args)
        mock_rbt.assert_called_once_with(args, 'aws')

    def test_main_multi_clouds(self):
        args = Namespace(controller=['aws', 'gce'])
        with patch('cloudweatherreport.cloud_weather_report.run_bundle_test',
                   autospec=True) as mock_rbt:
            cloud_weather_report.main(args)
        calls = [call(args, 'aws'), call(args, 'gce')]
        self.assertEqual(mock_rbt.mock_calls, calls)
