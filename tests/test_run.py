from unittest import TestCase

import mock

with mock.patch('deployer.utils.get_juju_major_version', return_value=1):
    # deployer (from bundletester) tries to call out to Juju CLI
    # on import to determine which major version of Juju it's using
    from cloudweatherreport import run
from cloudweatherreport import model


class TestRunner(TestCase):
    @mock.patch.object(model.TestPlan, 'load_plans')
    def test_run(self, mload_plans):
        mload_plans.return_value = [mock.Mock(), mock.Mock()]
        runner = run.Runner('aws', mock.Mock())
        runner.run_plan = mock.Mock()
        runner.run()
        self.assertEqual(runner.run_plan.call_args_list,
                         [mock.call(p) for p in mload_plans.return_value])

    def test_load_index(self):
        runner = run.Runner('aws', mock.Mock())
        datastore = mock.Mock()
        datastore.read.return_value = '{"providers": ["foo"]}'

        datastore.exists.return_value = True
        r1 = runner.load_index(datastore)
        self.assertIsInstance(r1, model.ReportIndex)
        self.assertEqual(r1.providers, ['foo'])

        datastore.exists.return_value = False
        r2 = runner.load_index(datastore)
        self.assertIsInstance(r2, model.ReportIndex)
        self.assertEqual(r2.providers, [])

    @mock.patch.object(model.Report, 'upsert_benchmarks')
    def test_load_report(self, mupsert_benchmarks):
        runner = run.Runner('aws', mock.Mock(test_id='test'))
        test_plan = mock.Mock(bundle='bundle')
        test_plan.report_filename.return_value = 'filename'
        datastore = mock.Mock()
        datastore.read.return_value = '{"test_id": "foo"}'
        index = mock.Mock()
        index.find_previous_report.return_value = mock.Mock()

        datastore.exists.return_value = True
        r1 = runner.load_report(datastore, index, test_plan)
        self.assertIsInstance(r1, model.Report)
        self.assertEqual(r1.test_id, 'foo')

        datastore.exists.return_value = False
        r2 = runner.load_report(datastore, index, test_plan)
        self.assertIsInstance(r2, model.Report)
        self.assertEqual(r2.test_id, 'test')
        assert mupsert_benchmarks.called

    def test_run_plan(self):
        self.skipTest('Not implemented')

    def test_run_tests(self):
        self.skipTest('Not implemented')

    def test_run_benchmarks(self):
        self.skipTest('Not implemented')

    def test_fetch_svg(self):
        self.skipTest('Not implemented')
