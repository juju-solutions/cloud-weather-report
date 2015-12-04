from datetime import datetime
import json
import os

from jinja2 import (
    Environment,
    FileSystemLoader,
)

__metaclass__ = type

ISO_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


class Reporter:
    """Generate report page."""

    def __init__(self, bundle, results, options):
        self.bundle = bundle
        self.results = results
        self.options = options
        self.pass_str = 'PASS'
        self.fail_str = 'FAIL'
        self.all_passed_str = 'All Passed'
        self.all_failed_str = 'All Failed'
        self.some_failed_str = 'Some Failed'

    def generate(self, html_filename, json_filename):
        json_content = self.generate_json(output_file=json_filename)
        past_results, _ = self.get_past_test_results(json_filename)
        self.generate_html(
            json_content=json_content, output_file=html_filename,
            past_results=past_results)

    def generate_html(self, json_content, output_file=None, past_results=None):
        env = Environment(loader=FileSystemLoader(searchpath='templates'))
        env.filters['humanize_date'] = humanize_date
        template = env.get_template('base.html')
        results = json.loads(json_content)
        html_content = template.render(
            title=self.bundle, charm_name=self.bundle, results=results,
            past_results=past_results)
        if output_file:
            with open(output_file, 'w') as stream:
                stream.write(html_content)
        return html_content

    def _to_str(self, return_code):
        return self.pass_str if return_code == 0 else self.fail_str

    def get_test_outcome(self, results):
        test_results = [True if r == self.pass_str else False for r in results]
        if all(test_results):
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
        for result in self.results:
            for test in result["test_results"]['tests']:
                str_result = self._to_str(test["returncode"])
                outcomes.append(
                    {'name': test["test"],
                     'result': str_result,
                     'duration': test["duration"],
                     })
                test_outcomes.append(str_result)
            output["results"].append(
                {"provider_name": result['provider_name'],
                 "tests": outcomes,
                 "info": result['info'],
                 "test_outcome": self.get_test_outcome(test_outcomes)})
            outcomes = []
            test_outcomes = []

        json_result = json.dumps(output, indent=2)
        if output_file:
            with open(output_file, 'w') as fp:
                fp.write(json_result)
        return json_result

    def get_past_test_results(self, filename):
        dir = os.path.dirname(filename)
        files = [os.path.join(dir, f) for f in os.listdir(dir)
                 if f.startswith(self.bundle) and f.endswith('.json')]
        try:
            files.remove(filename)
        except ValueError:
            pass
        results = []
        for f in files:
            with open(f) as fp:
                results.append(json.load(fp))
        results = sorted(results, key=lambda r: r["date"], reverse=True)
        return results, files


def humanize_date(value, input_format=ISO_TIME_FORMAT):
    value = datetime.strptime(value, input_format)
    return value.strftime("%b %d, %Y at %H:%M")
