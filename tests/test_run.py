import unittest
import argparse
import os
import mock
from shutil import rmtree
from tempfile import mkdtemp
from cloudweatherreport.datastore import DataStore


with mock.patch('deployer.utils.get_juju_major_version', return_value=1):
    # deployer (from bundletester) tries to call out to Juju CLI
    # on import to determine which major version of Juju it's using
    from cloudweatherreport import run
from cloudweatherreport import model


class TestRunner(unittest.TestCase):
    def setUp(self):
        self._pgvja = mock.patch.object(run, 'get_versioned_juju_api')
        self.mgvja = self._pgvja.start()
        self.addCleanup(self._pgvja.stop)

        self._pgjmv = mock.patch.object(run, 'get_juju_major_version',
                                        return_value=2)
        self.mgjmv = self._pgjmv.start()
        self.addCleanup(self._pgjmv.stop)

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

    @mock.patch('cloudweatherreport.run.logging.error')
    @mock.patch('cloudweatherreport.run.connect_juju_client')
    def test_run_plan_no_env(self, mock_juju, mock_logging):
        mock_juju.return_value = None
        runner = run.Runner('aws', mock.Mock())
        res = runner.run_plan(mock.Mock())
        assert mock_juju.called
        assert mock_logging.called
        self.assertFalse(res)

    @mock.patch('cloudweatherreport.run.DataStore.get')
    @mock.patch('cloudweatherreport.run.get_provider_name')
    @mock.patch('cloudweatherreport.run.connect_juju_client')
    def test_run_plan(self, mock_juju, mock_provider, mock_datastore):
        env = mock.Mock(spec=['provider_name', 'info'])
        env.info.return_value = {"ProviderType": "foo"}
        mock_juju.return_value = env
        mock_provider.return_value = "foo-provider"
        tempdir = mkdtemp()
        ds = DataStore.get(tempdir)
        mock_datastore.return_value = ds
        with mock.patch.object(run.Runner, 'run_tests',
                               return_value=mock.Mock()) as mock_result:
            with mock.patch.object(run.Runner, 'run_benchmarks',
                                   return_value="") as mock_benchmark:
                with mock.patch.object(run.Runner, 'load_index',
                                       return_value=mock.Mock()) as mock_index:
                    with mock.patch.object(run.Runner, 'load_report',
                                           return_value=mock.Mock()
                                           ) as mock_load:
                        runner = run.Runner('aws', mock.Mock())
                        runner.run_plan(mock.Mock())
        rmtree(tempdir)
        # Assert we tried to get the Juju env run the tests and benchmarks
        # and load the report and index
        assert mock_juju.called
        assert mock_result.called
        assert mock_benchmark.called
        assert mock_index.called
        assert mock_load.called
        self.assertTrue(True)

    @mock.patch('cloudweatherreport.run.get_provider_name')
    @mock.patch('cloudweatherreport.run.connect_juju_client')
    def test_run_plan_fail(self, mock_juju, mock_provider):
        env = mock.Mock(spec=['provider_name', 'info'])
        env.info.return_value = {"ProviderType": "foo"}
        mock_juju.return_value = env
        mock_provider.return_value = "foo-provider"
        with mock.patch.object(run.Runner, 'run_tests',
                               side_effect=Exception()) as mock_result:
            with mock.patch.object(run.Runner, 'run_benchmarks',
                                   return_value=""):
                runner = run.Runner('aws', mock.Mock())
                res = runner.run_plan(mock.Mock())
        # Assert we tried to get the Juju env run the tests but
        # since we failed to run the tests we return false
        assert mock_juju.called
        assert mock_result.called
        self.assertFalse(res)

    @mock.patch('bundletester.tester.main')
    @mock.patch.object(model.SuiteResult, 'from_bundletester_output')
    def test_run_tests(self, bt_out, tester_main):
        runner = run.Runner('aws', mock.Mock())
        env = mock.Mock()
        status = mock.Mock()
        status.bundle_yaml.return_value = mock.Mock()
        tester_main.return_value = status
        bt_out.return_value = status
        plan = mock.Mock()
        result = runner.run_tests(env, plan)
        # You called bundle tester and got back the results
        assert tester_main.called
        assert bt_out.called
        # The result is the Mock returned by SuiteResult
        self.assertIsInstance(result, mock.Mock)

    @mock.patch('cloudweatherreport.run.logging.error')
    @mock.patch('cloudweatherreport.run.find_unit')
    def test_run_benchmarks_action_fail(self, mock_unit, mock_log_error):
        mock_unit.return_value = "unit/0"
        env = mock.Mock()
        plan = self.get_plan()
        runner = run.Runner('aws', mock.Mock())
        runner.run_benchmarks(plan, env)
        assert mock_log_error.called

    @mock.patch('cloudweatherreport.run.find_unit')
    def test_run_benchmarks_unit_not_found(self, mock_unit):
        mock_unit.return_value = None
        env = mock.Mock()
        plan = self.get_plan()
        runner = run.Runner('aws', mock.Mock())
        with self.assertRaises(Exception):
            runner.run_benchmarks(plan, env)

    @mock.patch('cloudweatherreport.run.model.Benchmark.from_action')
    @mock.patch('cloudweatherreport.run.run_action')
    @mock.patch('cloudweatherreport.run.find_unit')
    def test_run_benchmarks(self, mock_unit, mock_action, mock_result):
        mock_unit.return_value = "unit/0"
        mock_action.return_value = mock.Mock()
        mock_result.return_value = "Result"
        env = mock.Mock()
        plan = self.get_plan()
        runner = run.Runner('aws', mock.Mock())
        benchmarks = runner.run_benchmarks(plan, env)
        self.assertEqual(len(benchmarks), 3)

    def get_plan(self):
        plan = model.TestPlan.from_dict({
            'bundle': 'bundle_name',
            'bundle_file': 'bundle.yaml',
            'tests': ['test1', 'test2'],
            'benchmark': {
                'unit/0': u'name1',
                'unit/1': {
                    u'name2': {
                        'param': 'value2',
                    },
                    u'name3': {
                        'param': 'value3',
                    },
                },
            },
        })
        return plan

    def test_parse_args_defaults(self):
        args = run.parse_args(['aws', 'test_plan', '--test-id', '1234'])
        expected = argparse.Namespace(
            bundle=None, controllers=['aws'], deployment=None, dryrun=False,
            exclude=None, failfast=True, juju_major_version=2,
            log_level='INFO', no_destroy=False, results_dir='results',
            skip_implicit=False, test_id='1234', test_pattern=None,
            test_plan='test_plan', testdir=os.getcwd(), tests_yaml=None,
            bucket=None, s3_creds=None, verbose=False)
        self.assertEqual(args, expected)


if __name__ == '__main__':
    unittest.main()
