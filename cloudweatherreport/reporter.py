import codecs
from datetime import datetime
import json
import logging
import os
import requests
import urllib

from jinja2 import (
    Environment,
    FileSystemLoader,
)

from cloudweatherreport.utils import file_prefix


__metaclass__ = type

ISO_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


class Reporter:
    """Generate report page."""

    def __init__(self, bundle, results, options, bundle_yaml=None):
        self.bundle = bundle
        self.results = results
        self.options = options
        self.bundle_yaml = bundle_yaml
        self.pass_str = 'PASS'
        self.fail_str = 'FAIL'
        self.all_passed_str = 'All Passed'
        self.all_failed_str = 'All Failed'
        self.some_failed_str = 'Some Failed'
        self.no_test_result = 'No test result'

    def generate(self, html_filename, json_filename):
        json_content = self.generate_json(output_file=json_filename)
        past_results, _ = self.get_past_test_results(json_filename)
        self.generate_html(
            json_content=json_content, output_file=html_filename,
            past_results=past_results)

    def generate_svg(self, filename):
        if not self.bundle_yaml:
            return None
        filename, ext = os.path.splitext(filename)
        svg_filename = "{}.svg".format(filename)
        r = requests.post('http://svg.juju.solutions', self.bundle_yaml)
        if r.status_code != requests.codes.ok:
            logging.warn("Could not generate svg. Response from "
                         "svg.juju.solutions: \n"
                         "Status code:{} \nContent: {}\n"
                         "bundle.yaml:\n{}".format(r.status_code, r.content,
                                                   self.bundle_yaml))
            return None
        with open(svg_filename, 'w') as fp:
            fp.write(r.content)
        return svg_filename

    def generate_html(self, json_content, output_file=None, past_results=None):
        env = Environment(loader=FileSystemLoader(searchpath='templates'))
        env.filters['humanize_date'] = humanize_date
        template = env.get_template('base.html')
        results = json.loads(json_content)
        svg_filename = "{}.svg".format(os.path.splitext(output_file)[0])
        svg_path = self.generate_svg(svg_filename)
        svg = urllib.quote(os.path.basename(svg_path)) if svg_path else None
        history = self.get_by_provider(past_results) if past_results else None
        html_content = template.render(
            title=self.bundle, charm_name=self.bundle, results=results,
            past_results=past_results, svg_path=svg, history=history,
            )
        if output_file:
            with codecs.open(output_file, 'w', encoding='utf-8') as stream:
                stream.write(html_content)
        return html_content

    def _to_str(self, return_code):
        return self.pass_str if return_code == 0 else self.fail_str

    def get_test_outcome(self, results):
        test_results = [True if r == self.pass_str else False for r in results]
        if not test_results:
            return self.no_test_result
        elif all(test_results):
            return self.all_passed_str
        elif not any(test_results):
            return self.all_failed_str
        else:
            return self.some_failed_str

    def generate_json(self, output_file=None):
        output = {
            "version": 1,
            "date": datetime.now().replace(microsecond=0).isoformat(),
            "path": output_file,
            "bundle": {
                "name": self.bundle,
                "services": None,
                "relations": None,
                "machines": None,
            },
            "results": []
        }
        outcomes = []
        test_outcomes = []
        benchmarks = []
        for result in self.results:
            for test in (result.get('test_results') or {}).get('tests', []):
                str_result = self._to_str(test["returncode"])
                outcomes.append(
                    {'name': test["test"],
                     'result': str_result,
                     'duration': format(test["duration"], '.2f'),
                     'output': test["output"],
                     'suite': test["suite"],
                     })
                test_outcomes.append(str_result)
            for benchmark in result.get('action_results', []):
                benchmarks.append(benchmark)

            output["results"].append(
                {"provider_name": result['provider_name'],
                 "tests": outcomes,
                 "info": result['info'],
                 "test_outcome": self.get_test_outcome(test_outcomes),
                 "benchmarks": benchmarks,
                 })
            outcomes = []
            test_outcomes = []
            benchmarks = []

        json_result = json.dumps(output, indent=2)
        if output_file:
            with codecs.open(output_file, 'w', encoding='utf-8') as fp:
                fp.write(json_result)
        return json_result

    def get_past_test_results(self, filename):
        dir = os.path.dirname(filename)
        files = [os.path.join(dir, f) for f in os.listdir(dir)
                 if f.startswith(file_prefix(self.bundle)) and
                 f.endswith('.json')]
        try:
            files.remove(filename)
        except ValueError:
            pass
        results = []
        for f in files:
            with codecs.open(f, 'r', encoding='utf-8') as fp:
                results.append(json.load(fp))
        results = sorted(results, key=lambda r: r["date"], reverse=True)
        return results, files

    def get_by_provider(self, results):
        outcome = {}
        for result in results:
            if result.get('results'):
                for test_result in result['results']:
                    key = test_result['provider_name']
                    if key in outcome:
                        outcome[key].append(result)
                    else:
                        outcome[key] = [result]
        return outcome


def humanize_date(value, input_format=ISO_TIME_FORMAT):
    value = datetime.strptime(value, input_format)
    return value.strftime("%b %d, %Y at %H:%M")
