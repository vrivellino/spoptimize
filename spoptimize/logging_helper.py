import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def setup_stream_handler():
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s: [%(filename)s:%(lineno)d %(funcName)s()] %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
