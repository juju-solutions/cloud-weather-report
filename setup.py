from __future__ import print_function

import os
import re
import subprocess
import setuptools
import sys


# If you see the following error, please install 'python-dev'
#   error: Setup script exited with error: command 'x86_64-linux-gnu-gcc
#   failed with exit status 1"


def check_tools():
    with open(os.devnull, 'wb') as dev_null:
        for tool in ('unzip', 'make'):
            try:
                subprocess.check_call([tool], stdout=dev_null, stderr=dev_null)
            except subprocess.CalledProcessError:
                pass
            except OSError:
                print("Error! install '{}' before continuing.".format(tool))
                return False
    return True


def install():
    with open('cloudweatherreport/__init__.py', 'rb') as fp:
        content = fp.read()
    version = str(re.search(r'__version__\s+=\s+\'(.*)\'', content).group(1))
    current_dir = os.path.abspath(os.path.dirname(__file__))
    req_path = os.path.join(current_dir, 'requirements.txt')
    with open(req_path) as fp:
        reqs = fp.read().splitlines()
    setuptools.setup(
        name='cloud-weather-report',
        author='Juju Developers',
        author_email='juju@lists.ubuntu.com',
        version=version,  # Update version in cloudweatherreport/__init__.py
        license='Affero GNU Public License v3',
        description='Assess Juju charms and benchmarks on the clouds.',
        url='https://github.com/juju-solutions/cloud-weather-report',
        zip_safe=False,
        packages=setuptools.find_packages(),
        include_package_data=True,
        entry_points={
            'console_scripts': [
                'cwr = cloudweatherreport.run:entry',
            ]
        },
        install_requires=reqs)


if __name__ == '__main__':
    status = check_tools()
    if not status:
        sys.exit(1)
    install()
