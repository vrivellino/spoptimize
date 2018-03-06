import copy
import datetime
import json
import unittest

import util
from logging_helper import logging, setup_stream_handler

logger = logging.getLogger()
logger.addHandler(logging.NullHandler())

sample_dict = {
    'level1a': {
        'level2list': ['string', datetime.datetime(2018, 3, 6, 9, 36, 2, 521173)]
    },
    'level1b': [
        {'list2B': [datetime.datetime(2018, 3, 6, 9, 36, 2, 521174), 'y']},
        {'2Bstring': 'test'},
        {'2B': datetime.datetime(2018, 3, 6, 9, 36, 2, 521175)}
    ]
}

sample_walked_dict = {
    'level1a': {
        'level2list': ['string', '2018-03-06T09:36:02.521173']
    },
    'level1b': [
        {'list2B': ['2018-03-06T09:36:02.521174', 'y']},
        {'2Bstring': 'test'},
        {'2B': '2018-03-06T09:36:02.521175'}
    ]
}


class JsonDumpsConverter(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None
        self.my_dict = copy.deepcopy(sample_dict)
        self.expected_loaded_json = copy.deepcopy(sample_walked_dict)

    def test_convert(self):
        logger.debug('JsonDumpsConverter.test_covert')
        res = json.dumps(self.my_dict, default=util.json_dumps_converter)
        self.assertDictEqual(json.loads(res), self.expected_loaded_json)


class WalkDictForDatetime(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None
        self.my_dict = copy.deepcopy(sample_dict)
        self.expected_res = copy.deepcopy(sample_walked_dict)

    def test_walk(self):
        logger.debug('WalkDictForDatetime.test_walk')
        util.walk_dict_for_datetime(self.my_dict)
        self.assertDictEqual(self.my_dict, self.expected_res)


if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)
    setup_stream_handler()
    unittest.main()
