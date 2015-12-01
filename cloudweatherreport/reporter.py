import json

from jinja2 import (
    Environment,
    FileSystemLoader,
)


__metaclass__ = type


class Reporter:
    """Generate report page."""

    def __init__(self, bundle, results, options):
        self.bundle = bundle
        self.results = results
        self.options = options

    def generate(self, html_filename, json_filename):
        json_content = self.generate_json(output_file=json_filename)
        self.generate_html(
            json_content=json_content, output_file=html_filename)

    def generate_html(self, json_content, output_file=None):
        env = Environment(loader=FileSystemLoader(searchpath='templates'))
        template = env.get_template('base.html')
        results = json.loads(json_content)
        html_content = template.render(
            title=self.bundle, charm_name=self.bundle, results=results)
        if output_file:
            with open(output_file, 'w') as stream:
                stream.write(html_content)
        return html_content

    def _to_str(self, return_code):
        return 'PASS' if return_code == 0 else "FAIL"

    def generate_json(self, output_file=None):
        output = {
            "version": 1,
            "bundle": {
                "name": self.bundle,
                "services": None,
                "relations": None,
                "machines": None,
            },
            "results": []
        }
        outcomes = []
        for result in self.results:
            cloud = result["env_name"]
            for test in result["test_results"]['tests']:
                outcomes.append(
                    {'name': test["test"],
                     'result': self._to_str(test["returncode"]),
                     'duration': test["duration"],
                     })
            output["results"].append({"cloud": cloud, "tests": outcomes})
            outcomes = []

        json_result = json.dumps(output, indent=2)
        if output_file:
            with open(output_file, 'w') as fp:
                fp.write(json_result)
        return json_result
