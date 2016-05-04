# Overview

Cloud Weather Report (cwr) enables charm authors and maintainers to run
health checks and benchmarks on multiple clouds.

When the `cwr` starts executing, it deploys a bundle or charm on the clouds
 chosen by the author. It runs all the tests associated with each charm
in each cloud it deployed to. It also runs benchmarks on those clouds allowing
charm authors to see how their charms are performing on different clouds.


## Installing prerequisites

Cloud Weather Report uses `make` and `unzip` during execution and `python-dev`
 during installation. Make sure these tools are installed before installing the
 `cwr`. If you are on Ubuntu, you can install them using `apt-get`.

## Installation

    [sudo] pip install cloud-weather-report
  
## Installing from a source
    
    curl -L -o cwr.zip https://github.com/juju-solutions/cloud-weather-report/archive/master.zip
    unzip cwr.zip
    cd cloud-weather-report-master
    python setup.py install

## Usage

After installing the Cloud Weather Report, you will have `cwr` command
installed on your machine. It is assumes that the controller is already bootstrapped
before running `cwr`. You can simply run `cwr` by specifying one or more
controllers and the path to the test plan.

    cwr controller  [controller ...] test-plan.yaml

For example if you already have bootstrapped `aws` and `gce` controllers:

    cwr aws gce test-plan.yaml
    

Note: `aws` and `gce` are the names of your Juju 1.25 environment (found in your environments.yaml) or the name of your Juju 2.0 controller (found in `juju list-controllers`). If you had named your environment or controller for AWS soemthing like `aws-west1` the CWR command would look like:

    cwr aws-west1 test-plan.yaml


Once `cwr` starts running, it deploys the bundle, runs the tests and benchmarks that
are defined in the test plan. An example of the test plan is included in the
`examples` directory. 

## Running bundles

The following is example of a test plan to run the `apache-analytics-sql` bundle. It
deploys `apache-analytics-sql` and runs `terasort` benchmarks.
  
    bundle: bundle:apache-analytics-sql
    benchmark:
        plugin:
            terasort

The following example deploys the `mongodb` charm and runs the `perf` benchmark.
The `runtime: 60` is a parameter passed to `perf`.


    bundle: cs:mongodb
    benchmark:
        mongodb:
            perf:
                runtime: 60


## Result outputs

Once the run is completed, the `cwr` generates a HTML file containing the test
and benchmark results. The path to the HTML file will be displayed and will also 
be opened in a web browser.
