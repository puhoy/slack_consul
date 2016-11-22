import unittest
import json

from slack_consul.slack_consul import get_diff_health
import logging

def load_json(path):
    with open(path) as f:
        j = json.load(f)
    return j


class TestDiff(unittest.TestCase):
    def test_new_health(self):
        old = {
            'passing': {},
            'warning': {},
            'critical': {}
        }
        new = load_json('tests/health_all_passing.json')
        d = get_diff_health(old_health=old, new_health=new)
        self.assertEquals(d['passing'], new['passing'])

    def test_one_critical(self):
        old = load_json('tests/health_all_passing.json')
        new = load_json('tests/health_one_critical.json')
        d = get_diff_health(old_health=old, new_health=new)
        self.assertEquals(d['critical'], new['critical'])
        self.assertEquals(d['warning'], {})
        self.assertEquals(d['passing'], {})
