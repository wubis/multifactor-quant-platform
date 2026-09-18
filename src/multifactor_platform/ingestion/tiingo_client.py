"""Cached EOD downloads with a persistent, conservative free-tier usage budget."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from zoneinfo import ZoneInfo
import json
import os
import re
import sqlite3

from multifactor_platform.ingestion.free_sources import TIINGO_FREE_LIMITS
from multifactor_platform.research import ResearchDataError


class QuotaExceeded(ResearchDataError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward an Authorization header to another host.


def _utc_now():
    return datetime.now(timezone.utc)


class TiingoClient:
    def __init__(self, token=None, cache_dir='data/external/tiingo', usage_db=None,
                 max_response_bytes=8_000_000, limits=None, transport=None, clock=_utc_now):
        self.token = token or os.environ.get('TIINGO_API_KEY')
        self.cache = Path(cache_dir)
        self.usage_db = Path(usage_db) if usage_db else self.cache / 'usage.sqlite'
        self.max_bytes = max_response_bytes
        if not isinstance(max_response_bytes, int) or max_response_bytes < 1:
            raise ValueError('max_response_bytes must be a positive integer')
        self.limits = dict(TIINGO_FREE_LIMITS)
        for key, value in (limits or {}).items():
            if key not in self.limits or not isinstance(value, int) or not 0 <= value <= self.limits[key]:
                raise ValueError('Local budgets may only reduce the free-tier limits')
            self.limits[key] = value
        self.transport = transport
        self.clock = clock
        self.account = sha256((self.token or 'no-token').encode()).hexdigest()

    @contextmanager
    def _db(self):
        self.usage_db.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.usage_db, timeout=30)
        connection.execute('''CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY, account TEXT, symbol TEXT, started REAL,
            month TEXT, bytes INTEGER, status TEXT)''')
        connection.execute('''CREATE TABLE IF NOT EXISTS cooldown (
            account TEXT PRIMARY KEY, until_time REAL)''')
        connection.execute('''CREATE TABLE IF NOT EXISTS cache (
            request_key TEXT PRIMARY KEY, receipt TEXT)''')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _reserve(self, symbol):
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError('Clock must return a timezone-aware datetime')
        stamp = now.timestamp()
        month = now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            cooldown = db.execute('SELECT until_time FROM cooldown WHERE account=?', (self.account,)).fetchone()
            if cooldown and cooldown[0] > stamp:
                raise QuotaExceeded('Tiingo returned a rate limit; requests remain paused for one hour')
            for seconds, key in [(3600, 'requests_per_hour'), (86400, 'requests_per_day')]:
                count = db.execute('SELECT count(*) FROM requests WHERE account=? AND started>?',
                                   (self.account, stamp - seconds)).fetchone()[0]
                if count >= self.limits[key]:
                    raise QuotaExceeded(f'Local {key} budget exhausted; resume after the window resets')
            symbols = {row[0] for row in db.execute(
                'SELECT DISTINCT symbol FROM requests WHERE account=? AND month=?', (self.account, month))}
            if symbol not in symbols and len(symbols) >= self.limits['unique_symbols_per_month']:
                raise QuotaExceeded('Monthly unique-symbol budget exhausted')
            used = db.execute('SELECT coalesce(sum(bytes),0) FROM requests WHERE account=? AND month=?',
                              (self.account, month)).fetchone()[0]
            if used + self.max_bytes > self.limits['bandwidth_bytes_per_month']:
                raise QuotaExceeded('Insufficient monthly bandwidth budget for a bounded response')
            row = db.execute('INSERT INTO requests(account,symbol,started,month,bytes,status) VALUES(?,?,?,?,?,?)',
                             (self.account, symbol, stamp, month, self.max_bytes, 'reserved'))
            return row.lastrowid

    def _fetch(self, url):
        request = Request(url, headers={'Authorization': f'Token {self.token}',
                                       'Accept': 'application/json', 'Accept-Encoding': 'identity'})
        try:
            with build_opener(_NoRedirect()).open(request, timeout=30) as response:
                data = response.read(self.max_bytes)
                return response.status, data
        except HTTPError as exc:
            # Provider bodies may echo request data. Do not print or persist them.
            return exc.code, b''
        except (URLError, TimeoutError, OSError):
            raise ResearchDataError('Tiingo transport failed; request remains charged to the local budget') from None

    def download(self, symbol, start_date, end_date, refresh=False):
        symbol = str(symbol).upper()
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9._-]{0,63}', symbol):
            raise ValueError('Invalid Tiingo symbol')
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
        if end < start:
            raise ValueError('end_date precedes start_date')
        parameters = {'symbol': symbol, 'startDate': str(start), 'endDate': str(end)}
        key = sha256(json.dumps([self.account, parameters], sort_keys=True).encode()).hexdigest()
        with self._db() as db:
            row = db.execute('SELECT receipt FROM cache WHERE request_key=?', (key,)).fetchone()
        if row and not refresh:
            receipt = json.loads(row[0])
            file = self.cache / 'responses' / f"{receipt['sha256']}.json"
            data = file.read_bytes()
            if sha256(data).hexdigest() != receipt['sha256']:
                raise ResearchDataError('Cached Tiingo response checksum mismatch')
            return {**receipt, 'cache_hit': True, 'path': str(file.resolve())}
        if not self.token:
            raise ResearchDataError('Set TIINGO_API_KEY in the process environment to download prices')
        request_id = self._reserve(symbol)
        url = f'https://api.tiingo.com/tiingo/daily/{quote(symbol)}/prices?' + urlencode(
            {'startDate': start_date, 'endDate': end_date, 'format': 'json'})
        # Tests inject a transport accepting URL and max bytes; it never receives the token.
        status, data = self.transport(url, self.max_bytes) if self.transport else self._fetch(url)
        if status != 200:
            with self._db() as db:
                db.execute('UPDATE requests SET status=? WHERE id=?', (f'http_{status}', request_id))
                if status == 429:
                    db.execute('INSERT OR REPLACE INTO cooldown VALUES(?,?)',
                               (self.account, (self.clock() + timedelta(hours=1)).timestamp()))
            raise ResearchDataError(f'Tiingo returned HTTP {status}; no retries or paid fallback were attempted')
        if len(data) >= self.max_bytes:
            raise ResearchDataError('Response reached the reserved byte cap; request a smaller date range')
        try:
            records = json.loads(data)
            required = {'date', 'open', 'high', 'low', 'close', 'adjClose', 'volume'}
            if not isinstance(records, list) or not records or any(not required.issubset(row) for row in records):
                raise ValueError('missing price rows')
            dates = [datetime.fromisoformat(row['date'].replace('Z', '+00:00')).date() for row in records]
            if len(set(dates)) != len(dates) or any(date < start or date > end for date in dates):
                raise ValueError('invalid price dates')
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ResearchDataError('Tiingo response did not contain unique EOD rows in the requested date range') from None
        digest = sha256(data).hexdigest()
        directory = self.cache / 'responses'
        directory.mkdir(parents=True, exist_ok=True)
        file = directory / f'{digest}.json'
        if file.exists():
            if file.read_bytes() != data:
                raise ResearchDataError('Immutable response conflict')
        else:
            with file.open('xb') as handle:
                handle.write(data)
        receipt = {**parameters, 'sha256': digest, 'retrieved_at': self.clock().isoformat(),
                   'source': 'tiingo_eod', 'bytes': len(data)}
        # The response body is immutable; the request cache points at its latest requested vintage.
        receipt_bytes = json.dumps(receipt, sort_keys=True, indent=2).encode()
        receipt_dir = self.cache / 'receipts'
        receipt_dir.mkdir(exist_ok=True)
        receipt_path = receipt_dir / f'{sha256(receipt_bytes).hexdigest()}.json'
        if not receipt_path.exists():
            receipt_path.write_bytes(receipt_bytes)
        with self._db() as db:
            db.execute('UPDATE requests SET bytes=?,status=? WHERE id=?', (len(data), 'ok', request_id))
            db.execute('INSERT OR REPLACE INTO cache VALUES(?,?)', (key, json.dumps(receipt)))
        return {**receipt, 'cache_hit': False, 'path': str(file.resolve())}
