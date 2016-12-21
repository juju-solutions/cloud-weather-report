import re
import json
import yaml
import logging
from datetime import datetime
from base64 import b64encode

from pkg_resources import resource_filename
import jinja2

from cloudweatherreport import utils


try:
    basestring
except NameError:
    # basestring doesn't exist in Python 3
    basestring = str


log = logging.getLogger(__name__)


# ******** Base types

class ScalarField(object):
    """
    A wrapper for a field holding a single value, which performs basic
    type-checking when the field is assigned.
    """
    def __init__(self, field_name, field_type):
        self.name = field_name
        self.type = field_type
        self.value = None

    def set(self, value):
        if not isinstance(value, (type(None), self.type)):
            raise TypeError(
                'Invalid value for {}: {} (must be {} not {})'.format(
                    self.name, value, self.type, type(value)))
        self.value = value

    def get(self):
        return self.value


class ListField(list):
    """
    A wrapper for a field holding multiple items, which peforms basic
    type-checking of the items when the field is manipulated.
    """
    def __init__(self, field_name, item_type):
        self.name = field_name
        self.type = item_type
        super(ListField, self).__init__()

    def _validate_item(self, item):
        if not isinstance(item, self.type):
            raise TypeError(
                'Invalid item value for {}: {} (must be {})'.format(
                    self.name, item, self.type))

    def _validate_value(self, value):
        if not isinstance(value, (type(None), list, tuple)):
            raise TypeError('Invalid value for {}: {} (must be {})'.format(
                self.name, value, 'list or tuple'))
        for item in value or []:
            self._validate_item(item)

    def set(self, value):
        self._validate_value(value)
        if value:
            self[:] = list(value)

    def get(self):
        return self

    def append(self, item):
        self._validate_item(item)
        super(ListField, self).append(item)

    def insert(self, index, item):
        self._validate_item(item)
        super(ListField, self).insert(index, item)

    def __setitem__(self, index, item):
        self._validate_item(item)
        super(ListField, self).__setitem__(index, item)

    def extend(self, value):
        self._validate_value(value)
        super(ListField, self).extend(value)

    def __setslice__(self, i, j, value):
        self._validate_value(value)
        super(ListField, self).__setslice__(i, j, value)


class BaseMeta(type):
    """
    Metaclass used to implement model fields as properties so that they
    show up as attributes, which is helpful for debugging.
    """
    def __new__(meta, name, bases, attrs):
        for field_name, field_type in attrs['fields'].items():
            attrs[field_name] = property(
                lambda s, k=field_name: s._field_data[k].get(),
                lambda s, value, k=field_name: s._field_data[k].set(value))
        return type.__new__(meta, name, bases, attrs)


class BaseModel(object):
    """
    Base class for all model types, which provides fields with validation,
    and conversion to and from Python dictionaries and JSON.
    """
    __metaclass__ = BaseMeta
    fields = {}
    """
    A mapping of field names to their desired types, which will be validated.
    """

    def __init__(self, **kwargs):
        super(BaseModel, self).__setattr__('_field_data', {})
        for field_name, field_type in self.fields.items():
            if isinstance(field_type, list) and field_type:
                field_value = ListField(field_name, field_type[0])
            else:
                field_value = ScalarField(field_name, field_type)
            self._field_data[field_name] = field_value

        for field_name, value in kwargs.items():
            setattr(self, field_name, value)

    # explicitly disable hashing
    __hash__ = None

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return False
        for field in self.fields:
            if getattr(self, field) != getattr(other, field):
                return False
        return True

    def __repr__(self):
        fields = []
        for field_name in sorted(self.fields):
            if isinstance(getattr(self, field_name), (BaseModel, list)):
                continue
            fields.append('='.join([field_name,
                                    repr(getattr(self, field_name))]))
        return '<{model_name} {fields}>'.format(
            model_name=type(self).__name__,
            fields=' '.join(fields),
        )

    def _setattr(self, field_name, value):
        """
        Internal attribute setter that bypasses validation.
        """
        super(BaseModel, self).__setattr__(field_name, value)

    def __setattr__(self, field_name, value):
        """
        Attribute setter implementation that validates fields and disallows
        setting of non-existant, non-field attributes.
        """
        if not hasattr(self, field_name) and field_name not in self.fields:
            raise AttributeError('Invalid field: {}'.format(field_name))
        super(BaseModel, self).__setattr__(field_name, value)

    def as_dict(self):
        """
        Serialize this model instance to a Python dictionary.
        """
        def _convert(value):
            if isinstance(value, BaseModel):
                return value.as_dict()
            else:
                return value

        data = {}
        for field_name, field_type in self.fields.items():
            field_value = getattr(self, field_name)
            if isinstance(field_type, list) and field_type:
                _data = data[field_name] = []
                for item in field_value:
                    _data.append(_convert(item))
            else:
                data[field_name] = _convert(field_value)
        return data

    def as_json(self):
        """
        Serialize this model instance to JSON.
        """
        return json.dumps(self.as_dict(),
                          sort_keys=True,
                          encoding='utf8',
                          indent=2,
                          default=utils.serializer)

    def as_yaml(self):
        """
        Serialize this model instance to YAML.
        """
        return yaml.dump(self.as_dict(),
                         encoding='utf8',
                         indent=2)

    @classmethod
    def from_dict(cls, value):
        """
        Deserialize an instance of this model from a Python dictionary.

        The data will be validated during deserialization.
        """
        self = cls()

        def _convert(field_type, value):
            if not field_type:
                return None
            elif issubclass(field_type, BaseModel):
                return field_type.from_dict(value)
            elif issubclass(field_type, datetime) and \
                    isinstance(value, basestring):
                return datetime.strptime(value, utils.ISO_TIME_FORMAT)
            else:
                return value

        for field_name, field_value in value.items():
            if field_name not in self.fields:
                raise ValueError('Unknown field: {}'.format(field_name))
            field_type = self.fields[field_name]
            if isinstance(field_type, list) and field_type:
                if not isinstance(field_value, list):
                    raise ValueError('Expected list for {}: {}'.format(
                        field_name, field_value))
                field_type = field_type[0]
                setattr(self, field_name, [_convert(field_type, item)
                                           for item in field_value])
            else:
                setattr(self, field_name, _convert(field_type, field_value))
        return self

    @classmethod
    def from_json(cls, value):
        """
        Deserialize an instance of this model from a JSON string.

        The data will be validated during deserialization.
        """
        return cls.from_dict(json.loads(value))

    @classmethod
    def from_yaml(cls, value):
        """
        Deserialize an instance of this model from a YAML string.

        The data will be validated during deserialization.
        """
        return cls.from_dict(yaml.safe_load(value))


# ********  Cloud Weather Report models

class BenchmarkPlan(BaseModel):
    fields = {
        'unit': basestring,
        'action': basestring,
        'params': dict,
    }


class TestPlan(BaseModel):
    fields = {
        'benchmarks': list([BenchmarkPlan]),
        'bundle': basestring,
        'bundle_file': basestring,
        'bundle_name': basestring,
        'tests': list([basestring]),
        'url': basestring,
        'test_label': basestring,
    }

    @classmethod
    def load_plans(cls, filename):
        """
        Load a test_plan.yaml file.

        Returns a list of TestPlan instances.
        """
        with open(filename) as fp:
            return cls.from_dict_or_list(yaml.safe_load(fp))

    @classmethod
    def from_dict_or_list(cls, data):
        """
        Deserialize a TestPlan instance from either a single
        Python dictionary or a list of dictionaries.

        The data will be validated during deserialization.
        """
        if not isinstance(data, list):
            data = [data]
        return list(map(TestPlan.from_dict, data))

    @classmethod
    def from_dict(cls, data):
        """
        Deserialize a TestPlan instance from a Python dictionary.

        The data will be validated during deserialization.

        Benchmark plans are normalized into a more usable structure.
        """
        benchmarks = data.pop('benchmark', {})
        plan = super(TestPlan, cls).from_dict(data)
        if benchmarks:
            for unit, action_info in benchmarks.items():
                if isinstance(action_info, basestring):
                    action_info = {action_info: {}}
                for action, params in action_info.items():
                    plan.benchmarks.append(BenchmarkPlan(
                        unit=unit,
                        action=action,
                        params=params,
                    ))
        return plan

    def report_filename(self, test_id):
        return Report(
            test_id=test_id,
            bundle=BundleInfo(name=self.bundle_name, url=self.url),
        ).filename_json

    def old_report_filename(self, test_id):
        """
        Deprecated file name based on the `bundle` field instead of
        the `bundle_name` field.
        """
        return Report(
            test_id=test_id,
            bundle=BundleInfo(name=self.bundle, url=self.url),
        ).filename_json


class BundleInfo(BaseModel):
    fields = {
        'machines': None,
        'ref': basestring,
        'name': basestring,
        'relations': None,
        'services': None,
        'url': basestring,
        'test_label': basestring,
    }


class BenchmarkProviderResult(BaseModel):
    fields = {
        'provider': basestring,
        'value': float,
    }

    @classmethod
    def from_dict(cls, data):
        if isinstance(data.get('value'), (basestring, int)):
            # actions don't preserve type, so the value field comes
            # in as a string and needs to be coerced to a float
            # also, just in case, coerce ints to floats as well
            data['value'] = float(data['value'])
        return super(BenchmarkProviderResult, cls).from_dict(data)


class BenchmarkResult(BaseModel):
    fields = {
        'date': datetime,
        'test_id': basestring,
        'provider_results': list([BenchmarkProviderResult]),
    }

    def provider_result(self, provider):
        """
        Returns the value of this benchmark result for the given provider.
        """
        for result in self.provider_results:
            if result.provider == provider:
                return result

    def provider_value(self, provider):
        """
        Returns the value of this benchmark result for the given provider.
        """
        provider_result = self.provider_result(provider)
        if provider_result:
            return provider_result.value


class Benchmark(BaseModel):
    fields = {
        'name': basestring,
        'direction': basestring,
        'units': basestring,
        'results': list([BenchmarkResult]),
    }

    colors = [
        '#0000ee',  # Blue
        '#ff00ff',  # Magenta
        '#009900',  # Green
        '#ff8000',  # Orange
        '#00cccc',  # Cyan
        '#ee0000',  # Red
        '#aa0099',  # Purple
        '#006666',  # Dark Cyan
        '#999999',  # Gray
        '#dddd00',  # Yellow
        '#000000',  # Black
    ]

    @classmethod
    def from_action(cls, action_result):
        try:
            # actions don't preserve type, so coerce to float
            value = float(action_result['value'])
        except ValueError as e:
            log.warn('Skipping malformed benchmark value for %s: %s',
                     action_result['name'], e.message)
            value = None
        return cls(
            name=action_result['name'],
            direction=action_result['direction'],
            units=action_result['units'],
            results=[
                BenchmarkResult(
                    test_id=action_result['test_id'],
                    date=datetime.now(),
                    provider_results=[
                        BenchmarkProviderResult(
                            provider=action_result['provider'],
                            value=value,
                        ),
                    ],
                ),
            ],
        )

    @property
    def providers(self):
        return sorted({pr.provider
                       for r in self.results
                       for pr in r.provider_results})

    def result_by_test_id(self, test_id, create=False):
        for result in self.results:
            if result.test_id == test_id:
                return result
        if create:
            result = BenchmarkResult(
                test_id=test_id,
                date=datetime.now(),
            )
            self.results.append(result)
            return result

    def as_chart(self):
        """
        Serialize this Benchmark to chart data as a Python dict.

        The result is used to render a graph using Chart.js.
        """
        data = {
            'title': self.name,
            'labels': [r.test_id for r in self.results],
            'datasets': [],
        }
        min = None
        max = None
        for i, provider in enumerate(self.providers):
            dataset = {
                'label': provider,
                'fill': False,
                'borderColor': self.colors[i],
                'borderWidth': 2,
                'backgroundColor': self.colors[i],
                'lineTension': 0,
                'spanGaps': True,
                'data': [],
            }
            for result in self.results:
                value = result.provider_value(provider)
                dataset['data'].append(value)
                if value is None:
                    continue
                if min is None or value < min:
                    min = value
                if max is None or value > max:
                    max = value
            data['datasets'].append(dataset)
        data['min'] = min
        data['max'] = max
        return data

    def as_chart_json(self):
        """
        Serialize this Benchmark to chart data as a JSON string.

        The result is used to render a graph using Chart.js.
        """
        return json.dumps(self.as_chart(),
                          sort_keys=True,
                          encoding='utf8',
                          indent=2,
                          default=utils.serializer)


class TestResult(BaseModel):
    fields = {
        'duration': float,
        'name': basestring,
        'output': basestring,
        'result': basestring,
        'suite': basestring,
    }


class SuiteResult(BaseModel):
    fields = {
        'provider': basestring,
        'test_outcome': basestring,
        'tests': list([TestResult]),
        'bundle_yaml': basestring,
    }

    @classmethod
    def from_bundletester_output(cls, provider, output):
        result = cls(provider=provider)
        try:
            data = json.loads(output or '{}')
        except (TypeError, ValueError):
            data = {}
        any_pass = False
        any_fail = False
        any_infra = False
        for test in data.get('tests', []):
            test_name = test.get('test')
            returncode = test.get('returncode')
            output = test.get('output', '')
            lint_or_proof = test_name in ('charm-proof', 'make lint')
            is_exception = 'Traceback' in output
            lint_exception = lint_or_proof and is_exception
            no_result = None in (test_name, returncode)
            amulet_infra = returncode == 200 or 'SystemExit: 200' in output
            deploy_fail = test_name == 'juju-deployer'
            hook_fail = 'hook failed' in output
            timeout = 'TimeoutError' in output
            infra_fail = any([
                lint_exception,
                amulet_infra,
                deploy_fail and not hook_fail,
                timeout,
                no_result,
            ])
            if returncode == 0:
                any_pass = True
                result_code = 'PASS'
            elif infra_fail:
                any_infra = True
                result_code = 'INFRA'
            else:
                any_fail = True
                result_code = 'FAIL'
            result.tests.append(TestResult(
                name=test_name or 'Exception',
                duration=test.get('duration', 0.0),
                output=output,
                result=result_code,
                suite=test.get('suite', 'unknown'),
            ))
        if any_fail:
            result.test_outcome = 'FAIL'
        elif any_infra:
            result.test_outcome = 'INFRA'
        elif any_pass:
            result.test_outcome = 'PASS'
        else:
            result.test_outcome = 'NONE'
        return result


class Report(BaseModel):
    fields = {
        'version': int,
        'test_id': basestring,
        'date': datetime,
        'path': basestring,
        'results': list([SuiteResult]),
        'bundle': BundleInfo,
        'benchmarks': list([Benchmark]),
    }

    @property
    def providers(self):
        return sorted([r.provider for r in self.results])

    def provider_result(self, provider, create=False):
        """
        Find a SuiteResult for the named provider,
        optionally creating if not found.
        """
        for result in self.results:
            if result.provider == provider:
                return result
        if create:
            result = SuiteResult(provider=provider)
            self.results.append(result)
            return result

    def benchmark_by_name(self, benchmark_name, create=False):
        """
        Find a Benchmark by name, optionally creating if not found.
        """
        for benchmark in self.benchmarks:
            if benchmark.name == benchmark_name:
                return benchmark
        if create:
            benchmark = Benchmark(name=benchmark_name)
            self.benchmarks.append(benchmark)
            return benchmark

    def as_html(self, svg_data):
        """
        Serialize this report instance to an HTML page.
        """
        templates = resource_filename(__name__, 'templates')
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(templates))
        env.filters['humanize_date'] = utils.humanize_date
        env.filters['base64'] = b64encode

        template = env.get_template('bundle.html')
        html = template.render(report=self, svg_data=svg_data,
                               base_url='../../')
        return html

    def _filename(self):
        return '/'.join([
            re.sub(r'[^a-zA-Z0-9]', '_', self.bundle.name),
            self.test_id,
            'report',
        ])

    @property
    def filename_json(self):
        return self._filename() + '.json'

    @property
    def filename_html(self):
        return self._filename() + '.html'

    def upsert_result(self, result):
        """
        Add or replace a SuiteResult.

        The result will be replaced if it is for the same provider.
        """
        # serialize and deserialize to Python dict to ensure deep copy
        result = SuiteResult.from_dict(result.as_dict())
        existing = self.provider_result(result.provider)
        if existing:
            self.results[self.results.index(existing)] = result
        else:
            self.results.append(result)

    def upsert_benchmarks(self, benchmarks):
        """
        Add or replace one or more benchmarks.

        Accepts a single Benchmark instance or a list of instances.

        Benchmark results will be replaced if they are for the same
        benchmark name, test ID, and provider.
        """
        if not isinstance(benchmarks, (list, tuple)):
            benchmarks = [benchmarks]
        # serialize and deserialize to Python dict to ensure deep copy
        benchmarks = [Benchmark.from_dict(benchmark.as_dict())
                      for benchmark in benchmarks]
        for benchmark in benchmarks:
            existing_bm = self.benchmark_by_name(benchmark.name)
            if not existing_bm:
                self.benchmarks.append(benchmark)
                continue
            # matching benchmark name
            for res in benchmark.results:
                existing_res = existing_bm.result_by_test_id(res.test_id)
                if not existing_res:
                    existing_bm.results.append(res)
                    continue
                # matching test_id
                for pr in res.provider_results:
                    existing_pr = existing_res.provider_result(pr.provider)
                    if not existing_pr:
                        existing_res.provider_results.append(pr)
                        continue
                    # matching provider
                    idx = existing_res.provider_results.index(existing_pr)
                    existing_res.provider_results[idx] = pr


class ReportIndexItem(BaseModel):
    fields = {
        'test_id': basestring,
        'bundle_name': basestring,
        'date': datetime,
        'results': dict,  # e.g., {'aws': 'PASS'}
        'url': basestring,
        'test_label': basestring,
    }

    @classmethod
    def from_report(cls, report):
        return cls(
            bundle_name=report.bundle.name,
            test_id=report.test_id,
            date=report.date,
            results={
                result.provider: result.test_outcome
                for result in report.results
            },
        )

    def __eq__(self, other):
        if isinstance(other, Report):
            return (self.bundle_name == other.bundle.name and
                    self.test_id == other.test_id)
        return super(ReportIndexItem, self).__eq__(other)

    def update_from_report(self, report):
        self.results = self.results or {}
        self.results.update({
            result.provider: result.test_outcome
            for result in report.results
        })

    @property
    def filename_html(self):
        return Report(
            test_id=self.test_id,
            bundle=BundleInfo(name=self.bundle_name),
        ).filename_html

    @property
    def filename_json(self):
        return Report(
            test_id=self.test_id,
            bundle=BundleInfo(name=self.bundle_name),
        ).filename_json


class ReportIndex(BaseModel):
    fields = {
        'providers': list([basestring]),
        'reports': list([ReportIndexItem]),
    }
    full_index_filename_json = 'full_index.json'
    full_index_filename_html = 'full_index.html'
    summary_filename_html = 'index.html'
    summary_filename_json = 'index.json'

    def upsert_report(self, report):
        """
        Add or update a single report.
        """
        for index_item in self.reports:
            if index_item == report:
                index_item.update_from_report(report)
                break
        else:
            index_item = ReportIndexItem.from_report(report)
            self.reports.insert(0, index_item)
        self.providers = sorted(set(self.providers) | set(report.providers))

    def find_previous_report(self, report):
        """
        Search the index for the most recent report for the same bundle
        which was created just prior to the given report.
        """
        for index_item in self.reports:
            if index_item.bundle_name not in (report.bundle.name,
                                              report.bundle.ref):
                continue
            if index_item.date < report.date:
                return index_item
        return None

    def bundle_names(self):
        """
        Return a list of the names of bundles which have reports.
        """
        return set(report.bundle_name for report in self.reports)

    def as_json(self, bundle_name=None, limit=None):
        """
        Serialize this index to JSON.

        Optionally, only serialize reports for a given bundle.
        """
        reports = self.reports
        if bundle_name:
            reports = filter(lambda r: r.bundle_name == bundle_name, reports)
        if limit:
            reports = reports[:limit]
        temp_index = ReportIndex(
            providers=self.providers,
            reports=reports,
        )
        return super(ReportIndex, temp_index).as_json()

    def as_html(self, bundle_name=None, limit=None):
        """
        Serialize this index to an HTML page.

        Optionally, only serialize reports for a given bundle.
        """
        templates = resource_filename(__name__, 'templates')
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(templates))
        env.filters['humanize_date'] = utils.humanize_date
        reports = self.reports
        if bundle_name:
            reports = filter(lambda r: r.bundle_name == bundle_name, reports)
        if limit:
            reports = reports[:limit]

        template = env.get_template('index.html')
        html = template.render(
            bundle_name=bundle_name,
            reports=reports,
            providers=self.providers,
            base_url='../' if bundle_name else '',
        )
        return html

    def _summary_data(self):
        bundles = {}
        for report in self.reports:
            bundle_name = report.bundle_name
            if bundle_name not in bundles:
                # save (only) the first (most recent) report per bundle
                bundles[bundle_name] = {
                    'count': 0,
                    'report': report,
                    'index_filename': self.bundle_index_html(bundle_name),
                }
            bundles[bundle_name]['count'] += 1
        return bundles

    def summary_json(self):
        """
        Serialize this index to a JSON summary of all the bundles
        contained in the report.
        """
        return json.dumps(
            [{
                'bundle_name': name,
                'latest_result': result['report'].as_dict(),
            } for name, result in sorted(self._summary_data().items())],
            sort_keys=True,
            encoding='utf8',
            indent=2,
            default=utils.serializer)

    def summary_html(self):
        """
        Serialize this index to an HTML summary of all the bundles
        contained in the report.
        """
        templates = resource_filename(__name__, 'templates')
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(templates))
        env.filters['humanize_date'] = utils.humanize_date
        template = env.get_template('bundles.html')

        html = template.render(
            bundles=self._summary_data(),
            providers=self.providers,
        )
        return html

    def _bundle_index_filename(self, bundle_name, ext):
        return '/'.join([
            re.sub(r'[^a-zA-Z0-9]', '_', bundle_name),
            'index.%s' % ext])

    def bundle_index_html(self, bundle_name):
        return self._bundle_index_filename(bundle_name, 'html')

    def bundle_index_json(self, bundle_name):
        return self._bundle_index_filename(bundle_name, 'json')
