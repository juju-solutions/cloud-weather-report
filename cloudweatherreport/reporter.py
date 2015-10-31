from jinja2 import (
    Environment,
    FileSystemLoader,
)

__metaclass__ = type


class Reporter:
    """Generate report page."""

    def __init__(self, options, test_results, action_results):
        self.options = options
        self.test_results = test_results
        self.action_results = action_results

    def generate_html(self, output_file=None):
        env = Environment(loader=FileSystemLoader(searchpath='templates'))
        template = env.get_template('base.html')
        content = template.render(title=self.options.testdir)
        if output_file:
            with open(output_file, 'w') as stream:
                stream.write(content)
        return content
