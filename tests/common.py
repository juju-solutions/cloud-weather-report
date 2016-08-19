from contextlib import contextmanager
import logging
import os


def setup_test_logging(test_case):
    logger = logging.getLogger()
    orig_handlers = logger.handlers
    logger.handlers = []
    logger.disabled = True
    orig_level = logger.level
    test_case.addCleanup(restore_test_logging, orig_handlers, orig_level)


def restore_test_logging(orig_handler, orig_level):
    logger = logging.getLogger()
    logger.handlers = orig_handler
    logger.level = orig_level


@contextmanager
def temp_cwd(temp_dir):
    org_cwd = os.getcwd()
    os.chdir(temp_dir)
    try:
        yield
    finally:
        os.chdir(org_cwd)
