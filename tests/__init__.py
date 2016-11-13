import unittest
import json

from slack_consul.slack_consul import get_diff_services


def load_json(path):
    with open(path) as f:
        j = json.load(f)
    return j


class TestDiff(unittest.TestCase):
    def test_equal(self):
        j = load_json('tests/equal_services.json')
        old = j['old']
        new = j['new']

        print()
        empty = {'new_services': [],
                 'missing_services': [],
                 'new_nodes': {},
                 'missing_nodes': {}}
        diff = get_diff_services(old, new)
        self.assertEquals(empty, diff)


    def test_added_node(self):
        # service1 has second node
        j = load_json('tests/added_node.json')
        old = j['old']
        new = j['new']

        print()
        added_node = {'new_services': [],
                 'missing_services': [],
                 'new_nodes': {
                     'service1': ['node2']
                 },
                 'missing_nodes': {}}
        diff = get_diff_services(old, new)
        self.assertEquals(added_node, diff)

    def test_missing_service(self):
        # service1 has second node
        j = load_json('tests/missing_service.json')
        old = j['old']
        new = j['new']

        missing_service = {'new_services': [],
                 'missing_services': ['service1'],
                 'new_nodes': {},
                 'missing_nodes': {'service1': ['node1']}}
        diff = get_diff_services(old, new)
        self.assertEquals(missing_service, diff)

