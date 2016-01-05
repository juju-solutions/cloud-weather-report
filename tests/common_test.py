import logging


def setup_test_logging(test_case):
    logger = logging.getLogger()
    orig_handlers = logger.handlers
    logger.handlers = []
    orig_level = logger.level
    test_case.addCleanup(restore_test_logging, orig_handlers, orig_level)


def restore_test_logging(orig_handler, orig_level):
    logger = logging.getLogger()
    logger.handlers = orig_handler
    logger.level = orig_level
