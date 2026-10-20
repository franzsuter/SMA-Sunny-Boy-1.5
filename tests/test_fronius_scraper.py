import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import fronius_scraper as monitor


HTML = '<script id="__NEXT_DATA__">' + json.dumps({
    'props': {'pageProps': {'layoutData': {'sitecore': {'route': {'itemId': 'live-route'}}}}}
}) + '</script>'


def row(name='manual.pdf', title='Fronius Symo GEN24 3 - 5 kW Plus SC'):
    return {'title': title, 'link': '/~/downloads/Solar%20Energy/' + name,
            'type': 'Operating Instruction', 'language': 'DE', 'size': '23,4 MB', 'acceptAGB': False}


def response(rows, page=1, pages=1, total=None):
    return json.dumps({'general': {'usedSearchWord': monitor.ARTICLE_NUMBER}, monitor.DEPARTMENT: {
        'downloads': {'numberOfHits': len(rows) if total is None else total,
                      'numberOfPages': pages, 'page': page, 'results': rows}}})


class CatalogueTests(unittest.TestCase):
    def test_all_pages_and_product_scope(self):
        fetch = Mock(side_effect=[HTML, response([row()], pages=2, total=2),
                                  response([row('datasheet.pdf')], page=2, pages=2, total=2)])
        data = monitor.collect_documents(fetch)
        self.assertEqual(len(data), 2)
        for index, call in enumerate(fetch.call_args_list[1:], start=1):
            url, payload = call.args
            self.assertEqual(url, monitor.API_URL)
            self.assertEqual(payload['id'], 'live-route')
            self.assertEqual(payload['searchword'], '4,210,190,002')
            self.assertEqual(payload[monitor.DEPARTMENT], {'page': index, 'facets': []})
        document = next(iter(data.values()))
        self.assertEqual(document['Sprache'], 'DE')
        self.assertTrue(document['Link'].startswith('https://www.fronius.com/~/downloads/'))

    def test_incomplete_duplicate_and_changing_counts_fail(self):
        cases = [
            [response([row()], total=2)],
            [response([], total=0)],
            [response([row()], pages=2, total=2), response([row()], page=2, pages=2, total=2)],
            [response([row()], pages=2, total=2), response([row('other.pdf')], page=2, pages=2, total=3)],
            [response([row()], page=2)],
        ]
        for replies in cases:
            with self.subTest(replies=replies), self.assertRaises(monitor.ScanError):
                monitor.collect_documents(Mock(side_effect=[HTML] + replies))

    def test_rejects_wrong_product_unexpected_schema_and_links(self):
        wrong = json.loads(response([row()]))
        wrong['general']['usedSearchWord'] = 'other product'
        cases = ['<html>Access denied</html>', json.dumps(wrong), '{}',
                 response([dict(row(), link='javascript:alert(1)')]),
                 response([dict(row(), link='https://example.com/manual.pdf')]),
                 response([dict(row(), link='/de/download-center')]),
                 response([dict(row(), title='')])]
        for invalid in cases:
            with self.subTest(invalid=invalid), self.assertRaises(monitor.ScanError):
                monitor.collect_documents(Mock(side_effect=[HTML, invalid]))
        with self.assertRaises(monitor.ScanError):
            monitor.collect_documents(Mock(return_value='<html>No Next data</html>'))


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def test_new_unchanged_updated_and_history_limit(self):
        data = monitor.collect_documents(Mock(side_effect=[HTML, response([row()])]))
        self.assertEqual(monitor.update_snapshot(self.path, data, 'first'), 1)
        self.assertEqual(monitor.load_json(self.path / monitor.HISTORY_FILE, [])[0]['funde'][0]['typ'], 'NEU')
        self.assertEqual(monitor.update_snapshot(self.path, data, 'second'), 0)
        changed = copy.deepcopy(data)
        next(iter(changed.values()))['Groesse'] = '24 MB'
        self.assertEqual(monitor.update_snapshot(self.path, changed, 'third'), 1)
        self.assertEqual(monitor.load_json(self.path / monitor.HISTORY_FILE, [])[0]['funde'][0]['typ'], 'UPDATE')
        for i in range(35):
            monitor.update_snapshot(self.path, changed, str(i))
        self.assertEqual(len(monitor.load_json(self.path / monitor.HISTORY_FILE, [])), 30)

    def test_network_failure_preserves_snapshot_and_history(self):
        monitor.run(self.path, Mock(side_effect=[HTML, response([row()])]))
        before = {name: (self.path / name).read_bytes() for name in [monitor.DATA_FILE, monitor.HISTORY_FILE]}
        last_success = monitor.load_json(self.path / monitor.STATUS_FILE, {})['letzter_erfolg']
        with self.assertRaises(OSError):
            monitor.run(self.path, Mock(side_effect=OSError('network unavailable')))
        for name, content in before.items():
            self.assertEqual((self.path / name).read_bytes(), content)
        status = monitor.load_json(self.path / monitor.STATUS_FILE, {})
        self.assertFalse(status['ok'])
        self.assertEqual(status['letzter_erfolg'], last_success)
        # A later successful run clears the failure without generating false changes.
        monitor.run(self.path, Mock(side_effect=[HTML, response([row()])]))
        self.assertTrue(monitor.load_json(self.path / monitor.STATUS_FILE, {})['ok'])
        self.assertEqual(monitor.load_json(self.path / monitor.HISTORY_FILE, [])[0]['funde'], [])

    def test_failed_second_page_does_not_publish_partial_scan(self):
        monitor.run(self.path, Mock(side_effect=[HTML, response([row()])]))
        before = (self.path / monitor.DATA_FILE).read_bytes()
        with self.assertRaises(monitor.ScanError):
            monitor.run(self.path, Mock(side_effect=[HTML, response([row('new.pdf')], pages=2, total=2), '{}']))
        self.assertEqual((self.path / monitor.DATA_FILE).read_bytes(), before)

    def test_first_failure_creates_only_failure_status(self):
        with self.assertRaises(monitor.ScanError):
            monitor.run(self.path, Mock(side_effect=[HTML, response([], total=0)]))
        self.assertFalse((self.path / monitor.DATA_FILE).exists())
        self.assertFalse((self.path / monitor.HISTORY_FILE).exists())
        self.assertFalse(monitor.load_json(self.path / monitor.STATUS_FILE, {})['ok'])


if __name__ == '__main__':
    unittest.main()
