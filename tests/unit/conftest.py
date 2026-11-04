# -*- coding: utf-8 -*-

# Copyright (c) 2026, Ahmed Boukerram
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Test helpers: a fake Cloud Temple API and an ansible_collections tree.

The fake API serves the JSON fixtures (captured from a real tenant for the
virtual machines) so that the plugin is exercised end to end with the real
open_url, without credentials.
"""

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES = os.path.join(ROOT, 'tests', 'unit', 'fixtures')

# Make "ansible_collections.boukerramahmed.cloudtemple" importable from the repo.
COLLECTIONS_PATH = tempfile.mkdtemp(prefix='ct-collections-')
os.makedirs(os.path.join(COLLECTIONS_PATH, 'ansible_collections', 'boukerramahmed'))
os.symlink(ROOT, os.path.join(COLLECTIONS_PATH, 'ansible_collections',
                              'boukerramahmed', 'cloudtemple'))
sys.path.insert(0, COLLECTIONS_PATH)

CLIENT_ID = 'test-client-id'
SECRET_ID = 'test-secret-id'


def load_fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


class FakeApi:

    def __init__(self):
        self.vms = load_fixture('virtual_machines.json')['vms']
        self.adapters = load_fixture('network_adapters.json')
        self.floating_ips = load_fixture('floating_ips.json')
        self.floating_ips_status = 200
        self.tokens_issued = 0
        self.valid_token = None
        # status codes returned once, in order, before serving GET requests
        self.failures = []
        self.requests = []

    def handle(self, method, path, query, body):
        self.requests.append((method, path, query))
        if method == 'POST' and path == '/api/iam/v2/auth/personal_access_token':
            creds = json.loads(body)
            if creds != {'id': CLIENT_ID, 'secret': SECRET_ID}:
                return 401, {'message': 'invalid credentials'}
            self.tokens_issued += 1
            self.valid_token = 'header.payload%d.signature' % self.tokens_issued
            return 200, self.valid_token
        return None

    def get(self, path, query, token):
        if token != self.valid_token:
            return 401, {'message': 'expired token'}
        if self.failures:
            return self.failures.pop(0), {'message': 'injected failure'}
        if path == '/api/vm_instances/v1/virtual_machines':
            vms = self.vms
            if 'status' in query:
                vms = [vm for vm in vms if vm['status'] == query['status'][0]]
            limit = int(query.get('limit', ['200'])[0])
            offset = int(query.get('offset', ['0'])[0])
            return 200, {'vms': vms[offset:offset + limit], 'total': len(vms)}
        prefix = '/api/vm_instances/v1/virtual_machines/'
        if path.startswith(prefix) and path.endswith('/network_adapters'):
            vm_id = path[len(prefix):-len('/network_adapters')]
            return 200, self.adapters.get(
                vm_id, {'vmId': vm_id, 'networks': [], 'total': 0})
        if path == '/api/vpc/v1/floating_ips':
            if self.floating_ips_status != 200:
                return self.floating_ips_status, {'message': 'forbidden'}
            return 200, self.floating_ips
        return 404, {'message': 'not found'}


@pytest.fixture
def fake_api():
    api = FakeApi()

    class Handler(BaseHTTPRequestHandler):

        def _reply(self, status, payload):
            raw = payload if isinstance(payload, str) else json.dumps(payload)
            data = raw.encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            if status == 429:
                self.send_header('Retry-After', '0')
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            url = urlparse(self.path)
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            result = api.handle('POST', url.path, parse_qs(url.query), body)
            self._reply(*(result or (404, {'message': 'not found'})))

        def do_GET(self):
            url = urlparse(self.path)
            query = parse_qs(url.query)
            api.requests.append(('GET', url.path, query))
            auth = self.headers.get('Authorization', '')
            token = auth[len('Bearer '):] if auth.startswith('Bearer ') else None
            self._reply(*api.get(url.path, query, token))

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    api.url = 'http://127.0.0.1:%d/api' % server.server_address[1]
    yield api
    server.shutdown()
    server.server_close()
