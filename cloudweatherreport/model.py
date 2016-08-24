import re
import json
import yaml
from datetime import datetime
from base64 import b64encode

from pkg_resources import resource_filename
import jinja2

from cloudweatherreport import utils


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
            if issubclass(field_type, BaseModel):
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
            bundle=BundleInfo(name=self.bundle),
        ).filename_json


class BundleInfo(BaseModel):
    fields = {
        'machines': None,
        'name': basestring,
        'relations': None,
        'services': None,
    }


class BenchmarkProviderResult(BaseModel):
    fields = {
        'provider': basestring,
        'value': float,
    }


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
                            value=action_result['value'],
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
        for test in data.get('tests', []):
            if test['returncode'] == 0:
                any_pass = True
            else:
                any_fail = True
            result.tests.append(TestResult(
                name=test['test'],
                duration=test['duration'],
                output=test['output'],
                result='PASS' if test['returncode'] == 0 else 'FAIL',
                suite=test['suite'],
            ))
        if not data.get('tests', []):
            result.test_outcome = 'No Results'
        elif any_pass and not any_fail:
            result.test_outcome = 'PASS'
        elif not any_pass and any_fail:
            result.test_outcome = 'FAIL'
        else:
            result.test_outcome = 'Some Failed'
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
        html = template.render(report=self, svg_data=svg_data)
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
            return (self.bundle_name == other.bundle.name
                    and self.test_id == other.test_id)
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


class ReportIndex(BaseModel):
    fields = {
        'providers': list([basestring]),
        'reports': list([ReportIndexItem]),
    }
    filename_json = 'index.json'
    filename_html = 'index.html'

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
            if index_item.bundle_name != report.bundle.name:
                continue
            if index_item.date < report.date:
                return index_item
        return None

    def as_html(self):
        """
        Serialize this index to an HTML page.
        """
        templates = resource_filename(__name__, 'templates')
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(templates))
        env.filters['humanize_date'] = utils.humanize_date

        template = env.get_template('index.html')
        html = template.render(report_index=self)
        return html
