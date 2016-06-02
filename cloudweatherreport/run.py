from __future__ import print_function

import subprocess
import sys

from cloud_weather_report import (
    main,
    parse_args
)
from utils import read_file


def file_open_with_app(filename):
    opener = {'linux2': 'xdg-open', 'linux': 'xdg-open', 'darwin': 'open',
              'win32': 'start'}
    try:
        subprocess.call([opener[sys.platform], filename])
    except:
        pass


def entry():
    args = parse_args()
    test_plans = read_file(args.test_plan, 'yaml')
    test_plans = [test_plans] if isinstance(test_plans, dict) else test_plans
    for test_plan in test_plans:
        html_filename = main(args, test_plan)
        print("Test result:\n  {}".format(html_filename))
        file_open_with_app((html_filename))


if __name__ == '__main__':
    entry()
