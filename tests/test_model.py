import os
import re
from unittest import TestCase
from datetime import datetime

import mock
from bs4 import BeautifulSoup

from cloudweatherreport import model


class _MockModel(model.BaseModel):
    fields = {
        'test_int': int,
        'test_str': basestring,
        'test_list': list([int]),
    }


class _MockContainerModel(model.BaseModel):
    fields = {
        'test_model': _MockModel,
        'test_list': list([_MockModel]),
        'test_date': datetime,
    }


class TestScalarField(TestCase):
    def test_field(self):
        sf = model.ScalarField('name', int)
        self.assertEqual(sf.get(), None)

        self.assertRaises(TypeError, sf.set, 'foo')
        self.assertRaises(TypeError, sf.set, [1])

        sf.set(1)
        self.assertEqual(sf.get(), 1)

        sf.set(None)
        self.assertEqual(sf.get(), None)


class TestListField(TestCase):
    def test_field(self):
        lf = model.ListField('name', int)
        self.assertIs(lf.get(), lf)
        self.assertEqual(lf, [])

        self.assertRaises(TypeError, lf.set, 0)
        self.assertRaises(TypeError, lf.set, 'foo')
        self.assertRaises(TypeError, lf.set, ['foo'])
        self.assertRaises(TypeError, lf.append, 'foo')
        self.assertRaises(TypeError, lf.insert, 0, 'foo')
        self.assertRaises(TypeError, lf.extend, 0)
        self.assertRaises(TypeError, lf.extend, ['foo'])
        with self.assertRaises(TypeError):
            lf[:] = 0
        with self.assertRaises(TypeError):
            lf[:] = ['foo']

        lf.set([1, 2, 3])
        self.assertEqual(lf, [1, 2, 3])

        with self.assertRaises(TypeError):
            lf[0] = 'foo'

        lf.append(4)
        lf.insert(0, 0)
        lf[1] = -1
        lf.extend([5, 6])
        lf[2:4] = [-2, -3]
        self.assertEqual(lf, [0, -1, -2, -3, 4, 5, 6])


class TestBaseModel(TestCase):
    maxDiff = None

    def test_base(self):
        test_model = _MockModel()
        self.assertEqual(test_model.test_int, None)
        self.assertEqual(test_model.test_str, None)
        self.assertEqual(test_model.test_list, [])

        test_model = _MockModel(
            test_int=0,
            test_str='',
            test_list=[0],
        )
        self.assertEqual(test_model.test_int, 0)
        self.assertEqual(test_model.test_str, '')
        self.assertEqual(test_model.test_list, [0])

        test_model.test_int = 1
        test_model.test_str = 'something'
        test_model.test_list = [1]
        self.assertEqual(test_model.test_int, 1)
        self.assertEqual(test_model.test_str, 'something')
        self.assertEqual(test_model.test_list, [1])

        with self.assertRaises(TypeError):
            test_model.test_int = 'str'
        with self.assertRaises(TypeError):
            test_model.test_str = 0
        with self.assertRaises(TypeError):
            test_model.test_list[0] = 'str'
        with self.assertRaises(AttributeError):
            test_model.foo = None
        test_model._setattr('foo', None)
        self.assertEqual(repr(test_model),
                         "<_MockModel test_int=1 test_str='something'>")

    def test_as_dict(self):
        test_model = _MockContainerModel(
            test_model=_MockModel(
                test_int=1,
                test_str='foo',
                test_list=[1, 2],
            ),
            test_list=[
                _MockModel(
                    test_int=2,
                    test_str='bar',
                    test_list=[3, 4],
                ),
                _MockModel(
                    test_int=3,
                    test_str='qux',
                    test_list=[5, 6],
                ),
            ]
        )
        self.assertEqual(test_model.as_dict(), {
            'test_date': None,
            'test_model': {
                'test_int': 1,
                'test_str': 'foo',
                'test_list': [1, 2],
            },
            'test_list': [
                {
                    'test_int': 2,
                    'test_str': 'bar',
                    'test_list': [3, 4],
                },
                {
                    'test_int': 3,
                    'test_str': 'qux',
                    'test_list': [5, 6],
                },
            ]
        })

    def test_as_json(self):
        test_model = _MockModel(
            test_int=1,
            test_str='str'
        )
        self.assertEqual(
            test_model.as_json(),
            '{\n'
            '  "test_int": 1, \n'
            '  "test_list": [], \n'
            '  "test_str": "str"\n'
            '}')

    def test_as_yaml(self):
        test_model = _MockModel(
            test_int=1,
            test_str='str'
        )
        self.assertEqual(
            test_model.as_yaml(),
            'test_int: 1\n'
            'test_list: []\n'
            'test_str: str\n')

    def test_from_dict(self):
        test_model = _MockContainerModel.from_dict({
            'test_model': {
                'test_int': 1,
                'test_str': 'foo',
                'test_list': [1, 2],
            },
            'test_list': [
                {
                    'test_int': 2,
                    'test_str': 'bar',
                    'test_list': [3, 4],
                },
                {
                    'test_int': 3,
                    'test_str': 'qux',
                    'test_list': [5, 6],
                },
            ],
            'test_date': '2000-01-01T00:00:00',
        })
        self.assertIsInstance(test_model.test_model, _MockModel)
        self.assertEqual(len(test_model.test_list), 2)
        self.assertIsInstance(test_model.test_list[0], _MockModel)
        self.assertIsInstance(test_model.test_list[1], _MockModel)
        self.assertEqual(test_model.test_model.test_int, 1)
        self.assertEqual(test_model.test_model.test_str, 'foo')
        self.assertEqual(test_model.test_model.test_list, [1, 2])
        self.assertEqual(test_model.test_list[0].test_int, 2)
        self.assertEqual(test_model.test_list[0].test_str, 'bar')
        self.assertEqual(test_model.test_list[0].test_list, [3, 4])
        self.assertEqual(test_model.test_list[1].test_int, 3)
        self.assertEqual(test_model.test_list[1].test_str, 'qux')
        self.assertEqual(test_model.test_list[1].test_list, [5, 6])
        self.assertEqual(test_model.test_date, datetime(2000, 1, 1))
        with self.assertRaises(ValueError) as cm:
            _MockModel.from_dict({'test_list': 'bar'})
        self.assertEqual(str(cm.exception), 'Expected list for test_list: bar')

    def test_from_json(self):
        test_model = _MockModel.from_json(
            '{\n'
            '  "test_int": 1, \n'
            '  "test_list": [], \n'
            '  "test_str": "str"\n'
            '}')
        self.assertEqual(test_model.test_int, 1)
        self.assertEqual(test_model.test_str, 'str')
        self.assertEqual(test_model.test_list, [])

    def test_from_yaml(self):
        test_model = _MockModel.from_yaml(
            'test_int: 1\n'
            'test_list: []\n'
            'test_str: str\n')
        self.assertEqual(test_model.test_int, 1)
        self.assertEqual(test_model.test_str, 'str')
        self.assertEqual(test_model.test_list, [])


class TestTestPlan(TestCase):
    @mock.patch.object(model, 'yaml')
    @mock.patch.object(model, 'open', create=True)
    @mock.patch.object(model.TestPlan, 'from_dict_or_list')
    def test_load_plans(self, fdol, mopen, myaml):
        myaml.safe_load.return_value = 'yaml'
        model.TestPlan.load_plans('filename')
        mopen.assert_called_once_with('filename')
        fdol.assert_called_once_with('yaml')

    @mock.patch.object(model.TestPlan, 'from_dict')
    def test_from_dict_or_list(self, from_dict):
        from_dict.side_effect = lambda d: 'TestPlan(%s)' % d['key']

        result = model.TestPlan.from_dict_or_list({'key': 'value'})
        self.assertEqual(result, ['TestPlan(value)'])

        result = model.TestPlan.from_dict_or_list([
            {'key': 'first'},
            {'key': 'second'},
        ])
        self.assertItemsEqual(result, [
            'TestPlan(first)',
            'TestPlan(second)',
        ])

    def test_from_dict(self):
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
        self.assertIsInstance(plan, model.TestPlan)
        self.assertEqual(plan.bundle, 'bundle_name')
        self.assertEqual(plan.bundle_file, 'bundle.yaml')
        self.assertEqual(plan.tests, ['test1', 'test2'])
        self.assertItemsEqual(plan.benchmarks, [
            model.BenchmarkPlan(
                unit='unit/0',
                action='name1',
                params={},
            ),
            model.BenchmarkPlan(
                unit='unit/1',
                action='name2',
                params={'param': 'value2'},
            ),
            model.BenchmarkPlan(
                unit='unit/1',
                action='name3',
                params={'param': 'value3'},
            ),
        ])

    @mock.patch.object(model, 'Report')
    def test_report_filename(self, mReport):
        mReport.return_value.filename_json = 'report.json'
        plan = model.TestPlan(bundle='cs:my-bundle',
                              bundle_name='cs:my-charm')
        self.assertEqual(plan.report_filename('test-id'), 'report.json')
        mReport.assert_called_once_with(
            test_id='test-id',
            bundle=model.BundleInfo(name='cs:my-charm'),
        )


class TestBenchmarkProviderResult(TestCase):
    def test_from_dict(self):
        bpr = model.BenchmarkProviderResult.from_dict({'provider': 'aws',
                                                       'value': '2.0'})
        self.assertEqual(bpr.provider, 'aws')
        self.assertEqual(bpr.value, 2.0)

        bpr = model.BenchmarkProviderResult.from_dict({'provider': 'aws',
                                                       'value': 3.0})
        self.assertEqual(bpr.value, 3.0)


class TestBenchmarkResult(TestCase):
    def test_provider_result(self):
        br = model.BenchmarkResult(provider_results=[
            model.BenchmarkProviderResult(provider='aws'),
            model.BenchmarkProviderResult(provider='gce'),
        ])
        self.assertEqual(br.provider_result('aws').provider, 'aws')
        self.assertEqual(br.provider_result('gce').provider, 'gce')
        self.assertIsNone(br.provider_result('azure'))

    @mock.patch.object(model.BenchmarkResult, 'provider_result')
    def test_provider_value(self, provider_result):
        br = model.BenchmarkResult()

        provider_result.return_value = None
        self.assertIs(br.provider_value('foo'), None)

        provider_result.return_value = mock.Mock(value='test-value')
        self.assertEqual(br.provider_value('foo'), 'test-value')


class TestBenchmark(TestCase):
    def test_from_action(self):
        bm = model.Benchmark.from_action({
            'name': 'bm_name',
            'direction': 'bm_dir',
            'units': 'bm_units',
            'test_id': 'bm_tid',
            'provider': 'bm_prov',
            'value': '1.5',
        })
        self.assertEqual(bm.name, 'bm_name')
        self.assertEqual(bm.direction, 'bm_dir')
        self.assertEqual(bm.units, 'bm_units')
        self.assertEqual(bm.results[0].test_id, 'bm_tid')
        self.assertEqual(bm.results[0].provider_results[0].provider, 'bm_prov')
        self.assertEqual(bm.results[0].provider_results[0].value, 1.5)

        bm = model.Benchmark.from_action({
            'name': 'bm_name',
            'direction': 'bm_dir',
            'units': 'bm_units',
            'test_id': 'bm_tid',
            'provider': 'bm_prov',
            'value': 'foo',
        })
        self.assertIsNone(bm.results[0].provider_results[0].value)

    def test_providers(self):
        bm = model.Benchmark(
            results=[
                model.BenchmarkResult(
                    provider_results=[
                        model.BenchmarkProviderResult(provider='aws'),
                        model.BenchmarkProviderResult(provider='gce'),
                    ]),
                model.BenchmarkResult(
                    provider_results=[
                        model.BenchmarkProviderResult(provider='gce'),
                        model.BenchmarkProviderResult(provider='azure'),
                    ]),
            ])
        self.assertEqual(bm.providers, ['aws', 'azure', 'gce'])

    def test_result_by_test_id(self):
        bm = model.Benchmark(
            results=[
                model.BenchmarkResult(test_id='test1'),
                model.BenchmarkResult(test_id='test2'),
            ])
        self.assertEqual(bm.result_by_test_id('test1').test_id, 'test1')
        self.assertEqual(bm.result_by_test_id('test2').test_id, 'test2')
        self.assertIsNone(bm.result_by_test_id('test3'))
        self.assertEqual(bm.result_by_test_id('test3', create=True).test_id,
                         'test3')

    def test_as_chart(self):
        bm = model.Benchmark(
            name='terasort',
            results=[
                model.BenchmarkResult(
                    test_id='test_1',
                    provider_results=[
                        model.BenchmarkProviderResult(provider='aws',
                                                      value=2.0),
                        model.BenchmarkProviderResult(provider='gce',
                                                      value=1.5),
                    ]),
                model.BenchmarkResult(
                    test_id='test_2',
                    provider_results=[
                        model.BenchmarkProviderResult(provider='gce',
                                                      value=0.5),
                        model.BenchmarkProviderResult(provider='azure',
                                                      value=2.0),
                    ]),
            ])
        self.assertEqual(bm.as_chart(), {
            'title': 'terasort',
            'labels': ['test_1', 'test_2'],
            'min': 0.5,
            'max': 2.0,
            'datasets': [
                {
                    'label': 'aws',
                    'fill': False,
                    'borderColor': '#0000ee',
                    'borderWidth': 2,
                    'backgroundColor': '#0000ee',
                    'lineTension': 0,
                    'spanGaps': True,
                    'data': [
                        2.0,
                        None,
                    ],
                },
                {
                    'label': 'azure',
                    'fill': False,
                    'borderColor': '#ff00ff',
                    'borderWidth': 2,
                    'backgroundColor': '#ff00ff',
                    'lineTension': 0,
                    'spanGaps': True,
                    'data': [
                        None,
                        2.0,
                    ],
                },
                {
                    'label': 'gce',
                    'fill': False,
                    'borderColor': '#009900',
                    'borderWidth': 2,
                    'backgroundColor': '#009900',
                    'lineTension': 0,
                    'spanGaps': True,
                    'data': [
                        1.5,
                        0.5,
                    ],
                },
            ]})

    @mock.patch.object(model.Benchmark, 'as_chart')
    def test_as_char_json(self, as_chart):
        as_chart.return_value = {
            'data2': None,
            'data1': 'value1',
        }
        self.assertEqual(model.Benchmark().as_chart_json(),
                         '{\n  "data1": "value1", \n  "data2": null\n}')


class TestSuiteResult(TestCase):
    def test_from_bundletester_output(self):
        sr = model.SuiteResult.from_bundletester_output('aws', None)
        self.assertEqual(sr.provider, 'aws')
        self.assertEqual(sr.test_outcome, 'NONE')
        self.assertEqual(sr.tests, [])

        sr = model.SuiteResult.from_bundletester_output('aws', '...')
        self.assertEqual(sr.test_outcome, 'NONE')
        self.assertEqual(sr.tests, [])

        sr = model.SuiteResult.from_bundletester_output('aws', '{}')
        self.assertEqual(sr.test_outcome, 'NONE')
        self.assertEqual(sr.tests, [])

        sr = model.SuiteResult.from_bundletester_output('aws', '{"tests": []}')
        self.assertEqual(sr.test_outcome, 'NONE')
        self.assertEqual(sr.tests, [])

        sr = model.SuiteResult.from_bundletester_output(
            'aws',
            """{
                "tests": [
                    {
                        "suite": "bundle",
                        "test": "test1",
                        "duration": 0.5,
                        "output": "something",
                        "returncode": 0
                    },
                    {
                        "suite": "bundle",
                        "test": "test2",
                        "duration": 1.5,
                        "output": "else",
                        "returncode": 0
                    }
                ]
            }""")
        self.assertEqual(sr.test_outcome, 'PASS')

        sr = model.SuiteResult.from_bundletester_output(
            'aws',
            """{
                "tests": [
                    {
                        "suite": "bundle",
                        "test": "test1",
                        "duration": 0.5,
                        "output": "something",
                        "returncode": 1
                    },
                    {
                        "suite": "bundle",
                        "test": "test2",
                        "duration": 1.5,
                        "output": "else",
                        "returncode": 1
                    }
                ]
            }""")
        self.assertEqual(sr.test_outcome, 'FAIL')

        sr = model.SuiteResult.from_bundletester_output(
            'aws',
            """{
                "tests": [
                    {
                        "suite": "bundle",
                        "test": "test1",
                        "duration": 0.5,
                        "output": "something",
                        "returncode": 0
                    },
                    {
                        "suite": "bundle",
                        "test": "test2",
                        "duration": 1.5,
                        "output": "else",
                        "returncode": 1
                    }
                ]
            }""")
        self.assertEqual(sr.test_outcome, 'FAIL')
        self.assertEqual(sr.tests, [
            model.TestResult(
                suite="bundle",
                name="test1",
                duration=0.5,
                result="PASS",
                output="something",
            ),
            model.TestResult(
                suite="bundle",
                name="test2",
                duration=1.5,
                result="FAIL",
                output="else",
            ),
        ])
        self.assertEqual(sr.provider, 'aws')

        sr = model.SuiteResult.from_bundletester_output(
            'aws',
            """{
                "tests": [
                    {
                        "suite": "bundle",
                        "test": "charm-proof",
                        "duration": 0.5,
                        "output": "Traceback",
                        "returncode": 1
                    }
                ]
            }""")
        self.assertEqual(sr.test_outcome, 'INFRA')

        sr = model.SuiteResult.from_bundletester_output(
            'aws',
            """{
                "tests": [
                    {
                        "suite": "bundle",
                        "test": "charm-proof",
                        "duration": 0.5,
                        "output": "something",
                        "returncode": 1
                    }
                ]
            }""")
        self.assertEqual(sr.test_outcome, 'FAIL')

        sr = model.SuiteResult.from_bundletester_output(
            'aws',
            """{
                "tests": [
                    {
                        "suite": "bundle",
                        "test": "make lint",
                        "duration": 0.5,
                        "output": "Traceback",
                        "returncode": 1
                    }
                ]
            }""")
        self.assertEqual(sr.test_outcome, 'INFRA')

        sr = model.SuiteResult.from_bundletester_output(
            'aws',
            """{
                "tests": [
                    {
                        "suite": "bundle",
                        "test": "make lint",
                        "duration": 0.5,
                        "output": "something",
                        "returncode": 1
                    }
                ]
            }""")
        self.assertEqual(sr.test_outcome, 'FAIL')


class TestReport(TestCase):
    def test_providers(self):
        report = model.Report(results=[
            model.SuiteResult(provider='aws'),
            model.SuiteResult(provider='gce'),
            model.SuiteResult(provider='azure'),
        ])
        self.assertEqual(report.providers, ['aws', 'azure', 'gce'])

    def test_provider_result(self):
        report = model.Report()
        self.assertIsNone(report.provider_result('aws'))
        pr = report.provider_result('aws', create=True)
        self.assertIsInstance(pr, model.SuiteResult)
        self.assertEqual(pr.provider, 'aws')
        self.assertIs(report.provider_result('aws'), pr)
        self.assertIsNone(report.provider_result('gce'))
        pr2 = report.provider_result('gce', create=True)
        self.assertIsNot(pr2, pr)
        self.assertEqual(report.results, [pr, pr2])

    def test_benchmark_by_name(self):
        report = model.Report()
        self.assertIsNone(report.benchmark_by_name('foo'))
        bm = report.benchmark_by_name('foo', create=True)
        self.assertIsInstance(bm, model.Benchmark)
        self.assertEqual(bm.name, 'foo')
        self.assertIs(report.benchmark_by_name('foo'), bm)
        self.assertIsNone(report.benchmark_by_name('bar'))
        bm2 = report.benchmark_by_name('bar', create=True)
        self.assertIsNot(bm2, bm)
        self.assertEqual(report.benchmarks, [bm, bm2])

    def test_as_html_xml(self):
        test_dir = os.path.dirname(__file__)
        with open(os.path.join(test_dir, 'data/hadoop-processing.svg')) as fp:
            svg_data = fp.read()
        report = model.Report(
            test_id='test2',
            bundle=model.BundleInfo(name='cs:my-bundle'),
            results=[
                model.SuiteResult(
                    provider='aws',
                    test_outcome='PASS',
                    tests=[
                        model.TestResult(
                            suite='bundle',
                            name='charm proof',
                            result='PASS',
                            duration=0.5,
                            output="Some output"
                        ),
                        model.TestResult(
                            suite='bundle',
                            name='00-setup',
                            result='PASS',
                            duration=0.5,
                            output="Some other output"
                        ),
                        model.TestResult(
                            suite='mysql',
                            name='00-setup',
                            result='PASS',
                            duration=1.5,
                            output="Some more output"
                        ),
                    ],
                ),
                model.SuiteResult(
                    provider='gce',
                    test_outcome='Some Failed',
                    tests=[
                        model.TestResult(
                            suite='bundle',
                            name='charm proof',
                            result='PASS',
                            duration=0.5,
                        ),
                        model.TestResult(
                            suite='bundle',
                            name='00-setup',
                            result='PASS',
                            duration=0.5,
                        ),
                        model.TestResult(
                            suite='mysql',
                            name='00-setup',
                            result='FAIL',
                            duration=2.5,
                        ),
                    ],
                ),
            ],
            benchmarks=[
                model.Benchmark(
                    name='bench1',
                    results=[
                        model.BenchmarkResult(
                            test_id='test1',
                            provider_results=[
                                model.BenchmarkProviderResult(
                                    provider='aws',
                                    value=1.1,
                                ),
                                model.BenchmarkProviderResult(
                                    provider='gce',
                                    value=0.5,
                                ),
                            ]),
                        model.BenchmarkResult(
                            test_id='test2',
                            provider_results=[
                                model.BenchmarkProviderResult(
                                    provider='aws',
                                    value=1.2,
                                ),
                            ]),
                        model.BenchmarkResult(
                            test_id='test3',
                            provider_results=[
                                model.BenchmarkProviderResult(
                                    provider='aws',
                                    value=1.2,
                                ),
                                model.BenchmarkProviderResult(
                                    provider='gce',
                                    value=0.9,
                                ),
                            ]),
                        model.BenchmarkResult(
                            test_id='test4',
                            provider_results=[
                                model.BenchmarkProviderResult(
                                    provider='aws',
                                    value=1.0,
                                ),
                                model.BenchmarkProviderResult(
                                    provider='gce',
                                    value=1.2,
                                ),
                            ]),
                    ]),
                model.Benchmark(
                    name='bench2',
                    results=[
                        model.BenchmarkResult(
                            test_id='test1',
                            provider_results=[
                                model.BenchmarkProviderResult(
                                    provider='aws',
                                    value=2.1,
                                ),
                            ]),
                        model.BenchmarkResult(
                            test_id='test2',
                            provider_results=[
                                model.BenchmarkProviderResult(
                                    provider='aws',
                                    value=2.2,
                                ),
                            ]),
                    ]),
            ])
        html = report.as_html(None)
        soup = BeautifulSoup(html, 'html.parser')
        self.assertIn('Image not available', html)
        self.assertEqual(soup.title.text, 'cs:my-bundle')
        self.assertIn("display_chart(1, {", html)
        self.assertIn("display_chart(2, {", html)
        html = report.as_html(svg_data)
        self.assertNotIn('Image not available', html)
        self.assertIn('src="data:image/svg+xml;base64,', html)
        xml = report.as_xml()
        self.assertIn('Some other output', xml)
        self.assertIn('testsuite', xml)

    def test_filename_json(self):
        report = model.Report(
            test_id='test-id',
            bundle=model.BundleInfo(name='cs:my-bundle'),
        )
        self.assertEqual(report.filename_json,
                         'cs_my_bundle/test-id/report.json')

    def test_filename_html(self):
        report = model.Report(
            test_id='test-id',
            bundle=model.BundleInfo(name='cs:my-bundle'),
        )
        self.assertEqual(report.filename_html,
                         'cs_my_bundle/test-id/report.html')

    def test_upsert_result(self):
        result1 = model.SuiteResult(
            provider='aws',
            test_outcome='PASS',
            tests=[
                model.TestResult(
                    suite='bundle',
                    name='charm proof',
                    result='FAIL',
                    duration=0.5,
                ),
                model.TestResult(
                    suite='bundle',
                    name='00-setup',
                    result='FAIL',
                    duration=0.5,
                ),
            ],
        )
        result2 = model.SuiteResult(
            provider='aws',
            test_outcome='PASS',
            tests=[
                model.TestResult(
                    suite='bundle',
                    name='charm proof',
                    result='PASS',
                    duration=0.5,
                ),
            ],
        )
        result3 = model.SuiteResult(
            provider='gce',
            test_outcome='PASS',
            tests=[
                model.TestResult(
                    suite='bundle',
                    name='charm proof',
                    result='PASS',
                    duration=0.5,
                ),
            ],
        )
        report = model.Report(
            test_id='test2',
            bundle=model.BundleInfo(name='cs:my-bundle'),
        )
        report.upsert_result(result1)
        self.assertEqual(report.results, [result1])
        self.assertIsNot(report.results[0], result1)

        report.upsert_result(result2)
        self.assertEqual(report.results, [result2])

        report.upsert_result(result3)
        self.assertEqual(report.results, [result2, result3])

    def test_upsert_benchmarks(self):
        bm1 = model.Benchmark(
            name='a1',
            results=[
                model.BenchmarkResult(
                    test_id='t1',
                    provider_results=[
                        model.BenchmarkProviderResult(
                            provider='aws',
                            value=1.0,
                        ),
                    ],
                ),
            ],
        )
        bm2 = model.Benchmark(
            name='a2',
            results=[
                model.BenchmarkResult(
                    test_id='t1',
                    provider_results=[
                        model.BenchmarkProviderResult(
                            provider='aws',
                            value=1.0,
                        ),
                    ],
                ),
            ],
        )
        bm3 = model.Benchmark(
            name='a1',
            results=[
                model.BenchmarkResult(
                    test_id='t1',
                    provider_results=[
                        model.BenchmarkProviderResult(
                            provider='gce',
                            value=1.0,
                        ),
                    ],
                ),
            ],
        )
        bm4 = model.Benchmark(
            name='a1',
            results=[
                model.BenchmarkResult(
                    test_id='t1',
                    provider_results=[
                        model.BenchmarkProviderResult(
                            provider='aws',
                            value=1.0,
                        ),
                        model.BenchmarkProviderResult(
                            provider='gce',
                            value=1.0,
                        ),
                    ],
                ),
            ],
        )
        bm5 = model.Benchmark(
            name='a1',
            results=[
                model.BenchmarkResult(
                    test_id='t1',
                    provider_results=[
                        model.BenchmarkProviderResult(
                            provider='aws',
                            value=2.0,
                        ),
                    ],
                ),
                model.BenchmarkResult(
                    test_id='t2',
                    provider_results=[
                        model.BenchmarkProviderResult(
                            provider='aws',
                            value=3.0,
                        ),
                    ],
                ),
            ],
        )
        bm6 = model.Benchmark(
            name='a1',
            results=[
                model.BenchmarkResult(
                    test_id='t1',
                    provider_results=[
                        model.BenchmarkProviderResult(
                            provider='aws',
                            value=2.0,
                        ),
                        model.BenchmarkProviderResult(
                            provider='gce',
                            value=1.0,
                        ),
                    ],
                ),
                model.BenchmarkResult(
                    test_id='t2',
                    provider_results=[
                        model.BenchmarkProviderResult(
                            provider='aws',
                            value=3.0,
                        ),
                    ],
                ),
            ],
        )
        report = model.Report(
            test_id='test2',
            bundle=model.BundleInfo(name='cs:my-bundle'),
        )
        report.upsert_benchmarks(bm1)
        self.assertEqual(report.benchmarks, [bm1])
        self.assertIsNot(report.benchmarks[0], bm1)

        report.upsert_benchmarks([bm2, bm3])
        self.assertEqual(report.benchmarks, [bm4, bm2])

        report.upsert_benchmarks(bm5)
        self.assertEqual(report.benchmarks, [bm6, bm2])


class TestReportIndexItem(TestCase):
    def test_eq(self):
        rii1 = model.ReportIndexItem(test_id='test-id1', bundle_name='bundle')
        rii2 = model.ReportIndexItem(test_id='test-id2', bundle_name='bundle')
        rii3 = model.ReportIndexItem(test_id='test-id1', bundle_name='bundle')
        report1 = model.Report(
            test_id='test-id1',
            bundle=model.BundleInfo(name='bundle'),
        )
        report2 = model.Report(
            test_id='test-id2',
            bundle=model.BundleInfo(name='bundle'),
        )
        self.assertNotEqual(rii1, rii2)
        self.assertNotEqual(rii1, report2)
        self.assertEqual(rii1, rii3)
        self.assertEqual(rii1, report1)

    def test_from_report(self):
        report = model.Report(
            test_id='test_id',
            bundle=model.BundleInfo(name='bundle'),
            date=datetime.now(),
            results=[
                model.SuiteResult(provider='aws', test_outcome='PASS'),
                model.SuiteResult(provider='gce', test_outcome='FAIL'),
            ])
        rii = model.ReportIndexItem.from_report(report)
        self.assertEqual(rii.test_id, 'test_id')
        self.assertEqual(rii.bundle_name, 'bundle')
        self.assertEqual(rii.date, report.date)
        self.assertEqual(rii.results, {'aws': 'PASS', 'gce': 'FAIL'})

    def test_update_from_report(self):
        report = model.Report(
            test_id='test_id',
            bundle=model.BundleInfo(name='bundle'),
            date=datetime.now(),
            results=[
                model.SuiteResult(provider='aws', test_outcome='PASS'),
                model.SuiteResult(provider='gce', test_outcome='FAIL'),
            ])
        rii = model.ReportIndexItem(
            test_id='my-test',
            bundle_name='my-bundle',
            date=datetime(2000, 1, 1),
        )
        self.assertEqual(rii.test_id, 'my-test')
        self.assertEqual(rii.bundle_name, 'my-bundle')
        self.assertEqual(rii.date, datetime(2000, 1, 1))
        self.assertIsNone(rii.results)

        rii.update_from_report(report)
        self.assertEqual(rii.test_id, 'my-test')
        self.assertEqual(rii.bundle_name, 'my-bundle')
        self.assertEqual(rii.date, datetime(2000, 1, 1))
        self.assertEqual(rii.results, {'aws': 'PASS', 'gce': 'FAIL'})


class TestReportIndex(TestCase):

    def test_remove_by_bundle_name(self):
        report = model.Report(
            test_id='test',
            bundle=model.BundleInfo(name='foo'),
            date=datetime(2000, 1, 1),
            results=[
                model.SuiteResult(
                    provider='gce',
                    test_outcome='PASS',
                ),
            ])
        report_index = model.ReportIndex()
        report_index.upsert_report(report)
        report_2 = model.Report(
            test_id='test_2',
            bundle=model.BundleInfo(name='bar'),
            date=datetime(2000, 2, 2),
            results=[
                model.SuiteResult(
                    provider='aws',
                    test_outcome='PASS',
                ),
            ])
        report_index.upsert_report(report_2)
        removed_reports = report_index.remove_by_bundle_name('foo')
        self.assertEqual(len(removed_reports), 1)
        self.assertEqual(removed_reports[0].bundle_name, 'foo')
        self.assertEqual(len(report_index.reports), 1)
        self.assertEqual(report_index.reports[0].bundle_name, 'bar')

    def test_remove_by_bundle_name_dry_run(self):
        report = model.Report(
            test_id='test',
            bundle=model.BundleInfo(name='foo'),
            date=datetime(2000, 1, 1),
            results=[
                model.SuiteResult(
                    provider='gce',
                    test_outcome='PASS',
                ),
            ])
        report_index = model.ReportIndex()
        report_index.upsert_report(report)
        report_2 = model.Report(
            test_id='test_2',
            bundle=model.BundleInfo(name='bar'),
            date=datetime(2000, 2, 2),
            results=[
                model.SuiteResult(
                    provider='aws',
                    test_outcome='PASS',
                ),
            ])
        report_index.upsert_report(report_2)
        removed_reports = report_index.remove_by_bundle_name(
            'foo', dry_run=True)
        self.assertEqual(len(removed_reports), 1)
        self.assertEqual(removed_reports[0].bundle_name, 'foo')
        self.assertEqual(len(report_index.reports), 2)
        self.assertEqual(report_index.reports[0].bundle_name, 'bar')
        self.assertEqual(report_index.reports[1].bundle_name, 'foo')

    def test_upsert_report(self):
        ri = model.ReportIndex()

        self.assertEqual(ri.providers, [])
        self.assertEqual(len(ri.reports), 0)

        report = model.Report(
            test_id='test',
            bundle=model.BundleInfo(name='bundle'),
            date=datetime(2000, 1, 1),
            results=[
                model.SuiteResult(
                    provider='gce',
                    test_outcome='PASS',
                ),
            ])
        ri.upsert_report(report)
        self.assertEqual(ri.providers, ['gce'])
        self.assertEqual(len(ri.reports), 1)

        report.results.append(model.SuiteResult(
            provider='aws',
            test_outcome='FAIL',
        ))
        # we're not just storing a copy of the Report instance
        self.assertEqual(ri.providers, ['gce'])
        self.assertEqual(len(ri.reports), 1)
        ri.upsert_report(report)
        self.assertEqual(ri.providers, ['aws', 'gce'])
        self.assertEqual(len(ri.reports), 1)

        ri.upsert_report(model.Report(
            test_id='test2',
            bundle=model.BundleInfo(name='bundle'),
            date=datetime(2000, 1, 2)))
        self.assertEqual(len(ri.reports), 2)
        self.assertEqual(ri.reports[0].test_id, 'test2')

    def test_find_previous_report(self):
        ri = model.ReportIndex(
            reports=[
                model.ReportIndexItem(
                    test_id='test4',
                    bundle_name='bundle1',
                    date=datetime(2000, 1, 3),
                ),
                model.ReportIndexItem(
                    test_id='test3',
                    bundle_name='bundle2',
                    date=datetime(2000, 1, 2),
                ),
                model.ReportIndexItem(
                    test_id='test2',
                    bundle_name='bundle1',
                    date=datetime(2000, 1, 2),
                ),
                model.ReportIndexItem(
                    test_id='test1',
                    bundle_name='bundle1',
                    date=datetime(2000, 1, 1),
                ),
            ])
        report5 = model.Report(
            test_id='test5',
            bundle=model.BundleInfo(name='bundle3'),
            date=datetime(2000, 1, 3))
        report4 = model.Report(
            test_id='test4',
            bundle=model.BundleInfo(name='bundle1'),
            date=datetime(2000, 1, 3))
        report3 = model.Report(
            test_id='test3',
            bundle=model.BundleInfo(name='bundle2'),
            date=datetime(2000, 1, 2))

        self.assertIsNone(ri.find_previous_report(report5))
        self.assertIsNone(ri.find_previous_report(report3))
        pr = ri.find_previous_report(report4)
        self.assertEqual(pr.test_id, 'test2')
        self.assertEqual(pr.bundle_name, 'bundle1')
        self.assertEqual(pr.date, datetime(2000, 1, 2))

    def test_as_html(self):
        ri = model.ReportIndex(
            providers=['aws', 'azure', 'gce'],
            reports=[
                model.ReportIndexItem(
                    test_id='test4',
                    bundle_name='cs:bundle1',
                    date=datetime(2000, 1, 3),
                    results={'aws': 'PASS',
                             'azure': 'PASS',
                             'gce': 'FAIL'},
                ),
                model.ReportIndexItem(
                    test_id='test3',
                    bundle_name='cs:bundle2',
                    date=datetime(2000, 1, 2),
                    results={'aws': 'PASS',
                             'azure': 'PASS',
                             'gce': 'PASS'},
                ),
                model.ReportIndexItem(
                    test_id='test2',
                    bundle_name='cs:bundle1',
                    date=datetime(2000, 1, 2),
                    results={'aws': 'PASS',
                             'azure': 'FAIL',
                             'gce': 'PASS'},
                ),
                model.ReportIndexItem(
                    test_id='test1',
                    bundle_name='cs:bundle1',
                    date=datetime(2000, 1, 1),
                    results={'aws': 'PASS',
                             'azure': 'INFRA'},
                ),
            ])
        html = ri.as_html()
        from path import Path
        Path('/tmp/index.html').write_text(html)
        soup = BeautifulSoup(html, 'html.parser')
        results = {
            'PASS': u'\u2714',
            'FAIL': u'\u2718',
            'Some': u'\u2718',
            'Prov': u'\u25B2',
            'None': u'\u25ef',
        }
        expected = [
            (
                u'cs:bundle1',
                u'Jan 03, 2000 at 00:00',
                u'aws {PASS} azure {PASS} gce {FAIL}'.format(**results),
                u'cs_bundle1/test4/report.html',
            ),
            (
                u'cs:bundle2',
                u'Jan 02, 2000 at 00:00',
                u'aws {PASS} azure {PASS} gce {PASS}'.format(**results),
                u'cs_bundle2/test3/report.html',
            ),
            (
                u'cs:bundle1',
                u'Jan 02, 2000 at 00:00',
                u'aws {PASS} azure {Some} gce {PASS}'.format(**results),
                u'cs_bundle1/test2/report.html',
            ),
            (
                u'cs:bundle1',
                u'Jan 01, 2000 at 00:00',
                u'aws {PASS} azure {Prov} gce {None}'.format(**results),
                u'cs_bundle1/test1/report.html',
            ),
        ]
        for i, tr in enumerate(soup.find_all('tr', class_='result')):
            tds = tr.find_all('td')
            self.assertEqual(expected[i], (
                tds[0].text.strip(),
                tds[1].text.strip(),
                re.sub('\n+', ' ', tds[2].text.strip()),
                tds[0].find('a')['href'],
            ))
