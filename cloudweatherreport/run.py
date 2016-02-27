import subprocess
import sys

from cloud_weather_report import (
    main,
    parse_args
)


def file_open_with_app(filename):
    opener = {'linux2': 'xdg-open', 'linux': 'xdg-open', 'darwin': 'open',
              'win32': 'start'}
    try:
        subprocess.call([opener[sys.platform], filename])
    except:
        pass


def entry():
    args = parse_args()
    html_filename = main(args)
    print("Test result:\n  {}".format(html_filename))
    file_open_with_app((html_filename))


if __name__ == '__main__':
    entry()
