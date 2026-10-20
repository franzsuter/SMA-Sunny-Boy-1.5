"""Monitor the GEN24 download catalogue using the website's own search API."""
import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

BASE_URL = 'https://www.fronius.com'
SEARCH_URL = BASE_URL + '/de/download-center'
API_URL = BASE_URL + '/api/data/search/getdownloadcenter'
ARTICLE_NUMBER = '4,210,190,002'
DEPARTMENT = 'sbsSolarAndEnergy'
DATA_FILE = 'fronius_daten.json'
HISTORY_FILE = 'fronius_history.json'
STATUS_FILE = 'fronius_status.json'


class ScanError(RuntimeError):
    pass


def request(url, payload=None):
    """Respect system proxy/CA settings; retry transient transport/server errors."""
    headers = {'User-Agent': 'DocumentMonitor/1.0'}
    body = None
    if payload is not None:
        headers.update({'Content-Type': 'application/json; charset=utf-8',
                        'X-Requested-With': 'XMLHttpRequest'})
        body = json.dumps(payload).encode('utf-8')
    for attempt in range(3):
        try:
            with urlopen(Request(url, data=body, headers=headers), timeout=60) as response:
                return response.read().decode('utf-8')
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def route_id(html):
    soup = BeautifulSoup(html, 'html.parser')
    script = soup.find('script', id='__NEXT_DATA__')
    try:
        value = json.loads(script.string)['props']['pageProps']['layoutData']['sitecore']['route']['itemId']
        if not isinstance(value, str) or not value:
            raise ValueError('Missing route ID')
        return value
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ScanError('Die Downloadsuche hat keine gültige Seiten-ID.') from exc


def payload_for(item_id, page):
    payload = {
        'id': item_id, 'language': 'de', 'activeDepartment': DEPARTMENT,
        'initialSearch': True, 'searchword': ARTICLE_NUMBER,
    }
    for department in ('perfectcharging', 'perfectwelding', 'solarenergy',
                       'sbsWelding', DEPARTMENT):
        payload[department] = {'facets': [], 'page': page if department == DEPARTMENT else 1}
    return payload


def download_url(link):
    if not isinstance(link, str) or not link.strip():
        raise ScanError('Dokument ohne Download-Link.')
    parts = urlsplit(urljoin(BASE_URL, link))
    # Keep the URL's original escaping, but reject navigation and foreign hosts.
    if (parts.scheme != 'https' or parts.netloc != 'www.fronius.com'
            or not unquote(parts.path).startswith('/~/downloads/')):
        raise ScanError('Unerwarteter Download-Link in der Suchantwort.')
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ''))


def collect_documents(fetch=request):
    item_id = route_id(fetch(SEARCH_URL))
    documents = {}
    expected = None
    pages = None
    page = 1
    while True:
        try:
            response = json.loads(fetch(API_URL, payload_for(item_id, page)))
            if response['general']['usedSearchWord'] != ARTICLE_NUMBER:
                raise ValueError('Wrong product query')
            downloads = response[DEPARTMENT]['downloads']
            total, count = downloads['numberOfHits'], downloads['numberOfPages']
            rows = downloads['results']
            if (type(total) is not int or total <= 0 or type(count) is not int
                    or not 1 <= count <= 100 or downloads['page'] != page
                    or not isinstance(rows, list) or not rows):
                raise ValueError('Empty or invalid result page')
            if expected is None:
                expected, pages = total, count
            elif (total, count) != (expected, pages):
                raise ValueError('Result count changed during pagination')
            for row in rows:
                url = download_url(row['link'])
                title = row['title']
                if not isinstance(title, str) or not title.strip():
                    raise ValueError('Missing title')
                document = {'Titel': title.strip(), 'Link': url}
                for source, target in [('type', 'Dokumenttyp'), ('language', 'Sprache'), ('size', 'Groesse')]:
                    if not isinstance(row[source], str):
                        raise ValueError('Invalid document metadata')
                    document[target] = row[source]
                if type(row['acceptAGB']) is not bool:
                    raise ValueError('Invalid download protection flag')
                document['Geschuetzt'] = row['acceptAGB']
                if url in documents:
                    raise ValueError('Duplicate download across result pages')
                documents[url] = document
        except (KeyError, TypeError, ValueError) as exc:
            raise ScanError(f'Ungültige oder unvollständige Suchantwort auf Seite {page}.') from exc
        if page == pages:
            break
        page += 1
    if len(documents) != expected:
        raise ScanError(f'Unvollständiger Scan: {len(documents)} von {expected} Dokumenten.')
    return dict(sorted(documents.items()))


def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    return default


def save_json(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=4) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def update_snapshot(directory, documents, stamp):
    if not documents:
        raise ScanError('Keine Dokumente gefunden; der bisherige Bestand bleibt erhalten.')
    old = load_json(directory / DATA_FILE, {})
    history = load_json(directory / HISTORY_FILE, [])
    changes = []
    for url, document in documents.items():
        if url not in old or document != old[url]:
            changes.append({'url': url, 'bezeichnung': document['Titel'],
                            'typ': 'NEU' if url not in old else 'UPDATE'})
    history.insert(0, {'datum': stamp, 'funde': changes})
    save_json(directory / DATA_FILE, documents)
    save_json(directory / HISTORY_FILE, history[:30])
    return len(changes)


def run(directory, fetch=request):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(ZoneInfo('Europe/Zurich')).strftime('%d.%m.%Y %H:%M')
    previous_status = load_json(directory / STATUS_FILE, {})
    try:
        documents = collect_documents(fetch)
        changes = update_snapshot(directory, documents, stamp)
    except Exception as exc:
        save_json(directory / STATUS_FILE, {
            'ok': False, 'versuch': stamp,
            'letzter_erfolg': previous_status.get('letzter_erfolg'),
            'fehler': f'{type(exc).__name__}: {exc}',
        })
        raise
    save_json(directory / STATUS_FILE, {
        'ok': True, 'versuch': stamp, 'letzter_erfolg': stamp,
        'anzahl': len(documents), 'artikelnummer': ARTICLE_NUMBER,
    })
    print(f'Fronius: {len(documents)} Dokumente, {changes} neue/geänderte Einträge.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parent)
    run(parser.parse_args().data_dir)
