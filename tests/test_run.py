import argparse
from cStringIO import StringIO
import json
import os
from shutil import rmtree
from tempfile import mkdtemp
import unittest

import mock

from cloudweatherreport.datastore import DataStore
from cloudweatherreport.utils import temp_dir

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
        runner = run.Runner('aws', False, mock.Mock())
        runner.run_plan = mock.Mock()
        runner.run()
        self.assertEqual(runner.run_plan.call_args_list,
                         [mock.call(p) for p in mload_plans.return_value])

    def test_load_index(self):
        runner = run.Runner('aws', False, mock.Mock())
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
        runner = run.Runner('aws', False, mock.Mock(test_id='test'))
        test_plan = mock.Mock(bundle='bundle',
                              bundle_name='name',
                              url='example.com')
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
        runner = run.Runner('aws', False, mock.Mock())
        with mock.patch.object(
                run.Runner, 'save_result_in_datastore') as mock_srd:
            res = runner.run_plan(mock.Mock())
        assert mock_juju.called
        assert mock_logging.called
        self.assertFalse(res)
        assert mock_srd.called

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
        test_plan = mock.Mock()
        with mock.patch.object(run.Runner, 'run_tests',
                               return_value=mock.Mock()) as mock_result:
            with mock.patch.object(run.Runner, 'run_benchmarks',
                                   return_value="") as mock_benchmark:
                with mock.patch.object(run.Runner, 'load_index',
                                       return_value=mock.Mock()) as mock_index:
                    with mock.patch.object(run.Runner, 'load_report',
                                           return_value=mock.Mock()
                                           ) as mock_load:
                        mock_index.return_value.bundle_names. \
                            return_value = ['bundle']
                        mock_index.return_value.bundle_index_filename. \
                            return_value = 'bundle/index.html'
                        with mock.patch.object(
                                run.Runner, 'check_cloud_resource') as mock_cr:
                            runner = run.Runner('aws', False, mock.Mock())
                            runner.run_plan(test_plan)
        rmtree(tempdir)
        # Assert we tried to get the Juju env run the tests and benchmarks
        # and load the report and index
        assert mock_juju.called
        assert mock_result.called
        assert mock_benchmark.called
        assert mock_index.called
        assert mock_load.called
        self.assertTrue(True)
        mock_cr.assert_called_once_with(test_plan, {'ProviderType': 'foo'})

    @mock.patch('cloudweatherreport.run.get_provider_name')
    @mock.patch('cloudweatherreport.run.connect_juju_client')
    def test_run_plan_fail(self, mock_juju, mock_provider):
        env = mock.Mock(spec=['provider_name', 'info'])
        env.info.return_value = {"ProviderType": "foo"}
        mock_juju.return_value = env
        mock_provider.return_value = "foo-provider"
        test_plan = mock.Mock()
        with mock.patch.object(run.Runner, 'run_tests',
                               side_effect=Exception()) as mock_result:
            with mock.patch.object(run.Runner, 'run_benchmarks',
                                   return_value=""):
                with mock.patch.object(
                        run.Runner, 'check_cloud_resource') as mock_cr:
                    with mock.patch.object(
                            run.Runner, 'save_result_in_datastore') as mock_sr:
                        runner = run.Runner('aws', False, mock.Mock())
                        res = runner.run_plan(test_plan)
        # Assert we tried to get the Juju env run the tests but
        # since we failed to run the tests we return false
        assert mock_juju.called
        assert mock_result.called
        self.assertFalse(res)
        assert mock_sr.called
        mock_cr.assert_called_once_with(test_plan, {'ProviderType': 'foo'})

    def test_generate_test_result(self):
        result = run.Runner.generate_test_result('aws', 'smoke', 'error')
        self.assertIsInstance(result, model.SuiteResult)
        self.assertEqual(result.provider, 'aws')
        self.assertEqual(result.tests[0].name, 'smoke')
        self.assertEqual(result.tests[0].output, 'error')

    def test_generate_test_result_error(self):
        with self.assertRaisesRegexp(ValueError, 'Invalid test outcome value'):
            run.Runner.generate_test_result(
                'aws', 'smoke', 'error', test_outcome='foo')

    @mock.patch('bundletester.tester.main')
    @mock.patch.object(model.SuiteResult, 'from_bundletester_output')
    def test_run_tests(self, bt_out, tester_main):
        runner = run.Runner('aws', False, mock.Mock())
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

    @mock.patch('bundletester.tester.main')
    @mock.patch.object(model.SuiteResult, 'from_bundletester_output')
    def test_run_tests_with_args(self, bt_out, tester_main):
        args = run.parse_args(
            ['aws', 'test_plan', '--test-id', '1234', '--deploy-plan', 'foo',
             '--deploy-budget', 'bar', '--testdir', '/tmp/testdir',
             '--no-matrix'])
        runner = run.Runner('aws', False, args)
        env = mock.Mock(spec_set=['name', 'provider_name'])
        env.name = 'env-name'
        status = mock.Mock()
        status.bundle_yaml.return_value = mock.Mock(spec_set=[])
        tester_main.return_value = status
        bt_out.return_value = status
        plan = mock.Mock(spec_set=['tests', 'bundle_file', 'bundle'])
        plan.tests = 'foo-tests'
        plan.bundle_file = 'foo-bundle-file'
        plan.bundle = 'foo-bundle'
        str_io = StringIO()
        with mock.patch('cloudweatherreport.run.StringIO', autospec=True,
                        return_value=str_io) as string_mock:
            result = runner.run_tests(plan, env)
        expected_args = argparse.Namespace(
            bucket=None,
            bundle='foo-bundle-file',
            controllers=['aws'],
            deploy_budget='bar',
            deploy_plan='foo',
            deployment=None,
            dryrun=False,
            environment='env-name',
            exclude=None,
            failfast=True,
            juju_major_version=2,
            log_level='INFO',
            no_destroy=False,
            no_matrix=True,
            output=str_io,
            regenerate_index=False,
            remove_test=None,
            reporter='json',
            results_dir='results',
            results_per_bundle=40,
            s3_creds=None,
            s3_public=True,
            skip_implicit=False,
            test_id='1234',
            test_pattern=None,
            test_plan='test_plan',
            testdir='foo-bundle',
            tests='foo-tests',
            tests_yaml=None,
            verbose=False)
        tester_main.assert_called_once_with(expected_args)
        string_mock.assert_called_once_with()
        assert bt_out.called
        self.assertIsInstance(result, mock.Mock)

    @mock.patch('cloudweatherreport.run.logging.error')
    @mock.patch('cloudweatherreport.run.find_unit')
    def test_run_benchmarks_action_fail(self, mock_unit, mock_log_error):
        mock_unit.return_value = "unit/0"
        env = mock.Mock()
        plan = self.get_plan()
        runner = run.Runner('aws', False, mock.Mock())
        runner.run_benchmarks(plan, env)
        assert mock_log_error.called

    @mock.patch('cloudweatherreport.run.find_unit', side_effect=Exception)
    def test_run_benchmarks_unit_not_found(self, mock_unit):
        mock_unit.return_value = None
        env = mock.Mock()
        plan = self.get_plan()
        runner = run.Runner('aws', False, mock.Mock())
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
        runner = run.Runner('aws', False, mock.Mock())
        benchmarks = runner.run_benchmarks(plan, env)
        self.assertEqual(len(benchmarks), 3)

    def test_remove_test_by_bundle_name(self):
        index_json = {
            "providers": [
                "GCE"
            ],
            "reports": [
                {
                    "bundle_name": "foo",
                    "date": "2017-12-06T21:15:56",
                    "results": {
                        "AWS": "FAIL"
                    },
                    "test_id": "11",
                    "test_label": None,
                    "url": None,
                },
                {
                    "bundle_name": "bar",
                    "date": "2017-11-15T17:44:01",
                    "results": {
                        "Azure": "NONE"
                    },
                    "test_id": "22",
                    "test_label": None,
                    "url": None,
                }

            ]

        }
        with temp_dir() as results_dir:
            full_index = os.path.join(
                results_dir,  model.ReportIndex.full_index_filename_json)
            args = run.parse_args(
                ['aws', 'test_plan', '--remove-test', 'foo', "--results-dir",
                 results_dir])
            with open(full_index, 'w') as f:
                json.dump(index_json, f)
            runner = run.Runner(None, False, args)
            runner.remove_test_by_bundle_name()
            with open(full_index) as f:
                result_index = json.load(f)
            self.assertEqual(len(result_index["reports"]), 1)
            self.assertEqual(result_index["reports"][0]["bundle_name"], "bar")
            os.path.isfile(model.ReportIndex.full_index_filename_html)
            os.path.isfile(model.ReportIndex.summary_filename_html)
            os.path.isfile(model.ReportIndex.summary_filename_json)

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
        with mock.patch('os.getcwd') as mgetcwd:
            mgetcwd.return_value = '/foo'
            args = run.parse_args(['aws', 'test_plan', '--test-id', '1234'])
        expected = argparse.Namespace(
            bucket=None,
            bundle=None,
            controllers=['aws'],
            deploy_budget=None,
            deploy_plan=None,
            deployment=None,
            dryrun=False,
            exclude=None,
            failfast=True,
            juju_major_version=2,
            log_level='INFO',
            no_destroy=False,
            no_matrix=False,
            regenerate_index=False,
            remove_test=None,
            results_dir='results',
            results_per_bundle=40,
            s3_creds=None,
            s3_public=True,
            skip_implicit=False,
            test_id='1234',
            test_pattern=None,
            test_plan='test_plan',
            testdir='/foo',
            tests_yaml=None,
            verbose=False,
        )
        self.assertEqual(args, expected)

    @mock.patch(
        'cloudweatherreport.run.is_resource_available')
    def test_check_cloud_resource(self, ira_mock):
        cloud_resource = {'machines': 1, 'cpus': 2}
        test_plan = mock.Mock(
            cloud_resource=cloud_resource, spec_set=['cloud_resource'])
        cloud_info = {'cloud-tag': 'cloud-aws', 'cloud-region': 'us-west'}
        runner = run.Runner('aws', False, mock.Mock())
        runner.check_cloud_resource(test_plan, cloud_info)
        ira_mock.assert_called_once_with(
            cloud='aws', cpu_limit=None, credentials_name=None,
            instance_limit=None, num_of_cpus=2, num_of_instances=1,
            num_of_security_groups=1, region='us-west',
            security_group_limit=None)

    @mock.patch(
        'cloudweatherreport.run.is_resource_available')
    def test_check_cloud_resource_with_limits(self, ira_mock):
        cloud_resource = {'machines': 1, 'cpus': 2}
        test_plan = mock.Mock(
            cloud_resource=cloud_resource, spec_set=['cloud_resource'])
        cloud_info = {'cloud-tag': 'cloud-aws', 'cloud-region': 'us-west'}
        runner = run.Runner('aws', False, mock.Mock())
        os.environ['AWS_MACHINE_LIMIT'] = '10'
        os.environ['AWS_SECURITY_GROUP_LIMIT'] = '50'
        os.environ['AWS_CPU_LIMIT'] = '20'
        try:
            runner.check_cloud_resource(test_plan, cloud_info)
        finally:
            del os.environ['AWS_MACHINE_LIMIT']
            del os.environ['AWS_SECURITY_GROUP_LIMIT']
            del os.environ['AWS_CPU_LIMIT']
        ira_mock.assert_called_once_with(
            cloud='aws', cpu_limit=20, credentials_name=None,
            instance_limit=10, num_of_cpus=2, num_of_instances=1,
            num_of_security_groups=1, region='us-west',
            security_group_limit=50)


if __name__ == '__main__':
    unittest.main()
