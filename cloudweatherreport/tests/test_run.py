from argparse import Namespace
from tempfile import NamedTemporaryFile
from unittest import TestCase

from mock import (
    call,
    patch,
)

from run import entry
from tests.test_cloud_weather_report import (
    make_tst_plan,
    make_tst_plan_file,
)


class TestRun(TestCase):

    def test_entry(self):
        with NamedTemporaryFile() as test_plan:
            make_tst_plan_file(test_plan.name)
            with patch('run.main', return_value='/tmp/html') as mock_main:
                args = self.make_args(test_plan.name)
                with patch('run.parse_args', autospec=True,
                           return_value=args) as mock_pa:
                    with patch('run.file_open_with_app') as mock_fowp:
                        with patch('__builtin__.print') as mock_print:
                            entry()
        mock_main.assert_called_once_with(args, make_tst_plan())
        mock_pa.assert_called_once_with()
        mock_fowp.assert_called_once_with('/tmp/html')
        mock_print.assert_called_once_with('Test result:\n  /tmp/html')

    def test_entry_multi_test_plans(self):
        with NamedTemporaryFile() as test_plan:
            make_tst_plan_file(test_plan.name, multi_test_plans=True)
            with patch('run.main', return_value='/tmp/html') as mock_main:
                args = self.make_args(test_plan.name)
                with patch('run.parse_args', autospec=True,
                           return_value=args) as mock_pa:
                    with patch('run.file_open_with_app') as mock_fowp:
                        with patch('__builtin__.print'):
                            entry()
        mock_pa.assert_called_once_with()
        self.assertEqual(mock_fowp.mock_calls,
                         [call('/tmp/html'), call('/tmp/html')])
        test_plans = make_tst_plan(multi_test_plans=True)
        calls = [
            call(args, (test_plans[0])),
            call(args, (test_plans[1])),
        ]
        self.assertEqual(mock_main.mock_calls, calls)

    def make_args(self, test_plan):
        return Namespace(
            controller=['aws'], result_output=None,
            test_plan=test_plan, testdir='git', verbose=False)
