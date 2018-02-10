import datetime


def json_dumps_converter(o):
    if isinstance(o, datetime.datetime):
        return o.isoformat()
    raise TypeError("Unknown type")


def walk_dict_for_datetime(node):
    '''
    Converts any instance of datetime.datetime to isoformat in a collection
    '''
    if type(node) == dict:
        for key, item in node.items():
            if type(item) in [dict, list]:
                walk_dict_for_datetime(item)
            elif type(item) == datetime.datetime:
                node[key] = item.isoformat()
    if type(node) == list:
        for idx, item in enumerate(node):
            if type(item) in [dict, list]:
                walk_dict_for_datetime(item)
            elif type(item) == datetime.datetime:
                node[idx] = item.isoformat()
