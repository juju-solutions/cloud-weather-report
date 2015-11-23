from argparse import Namespace
from tempfile import NamedTemporaryFile
from unittest import TestCase

from cloudweatherreport.reporter import Reporter


class TestReporter(TestCase):

    def test_generate_html(self):
        args = Namespace(testdir='git')
        r = Reporter(args, None, None)
        with NamedTemporaryFile() as output:
            html_output = r.generate_html(output.name)
        self.assertEqual(html_output, self.get_html_code('git'))

    def get_html_code(self, title):
        return ('<!DOCTYPE html>\n<html lang="en">\n<head>\n    '
                '<meta charset="UTF-8">\n    <title>{}</title>\n</head>\n'
                '<body>\n\n</body>\n</html>'.format(title))
