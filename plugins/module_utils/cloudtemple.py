# -*- coding: utf-8 -*-

# Copyright (c) 2026, Ahmed Boukerram
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Minimal Cloud Temple (Shiva) API client.

Only uses the standard library and ansible's open_url so that the collection
has no Python dependency. The client authenticates with a Personal Access
Token (client id + secret id), keeps the short lived JWT (5 minutes) in memory
and transparently re-authenticates once when the API answers 401.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.urls import ConnectionError as UrlsConnectionError
from ansible.module_utils.urls import SSLValidationError, open_url

DEFAULT_API_URL = 'https://shiva.cloud-temple.com/api'
AUTH_PATH = '/iam/v2/auth/personal_access_token'
VMS_PATH = '/vm_instances/v1/virtual_machines'
FLOATING_IPS_PATH = '/vpc/v1/floating_ips'
# GET /vm_instances/v1/virtual_machines accepts at most limit=200
PAGE_SIZE = 200
RETRY_STATUSES = (429, 500, 502, 503, 504)
USER_AGENT = 'ansible-collection-boukerramahmed-cloudtemple'


class CloudTempleError(Exception):

    def __init__(self, message, status=None):
        super(CloudTempleError, self).__init__(message)
        self.status = status


def _unwrap(payload, *keys):
    """Return (items, total) from either a bare list or a wrapping object.

    The public OpenAPI spec documents bare arrays, but the live API wraps
    some listings (e.g. {"vms": [...], "total": N}), so accept both.
    """
    if payload is None:
        return [], None
    if isinstance(payload, list):
        return payload, None
    if isinstance(payload, dict):
        for key in keys:
            if isinstance(payload.get(key), list):
                return payload[key], payload.get('total')
    expected = 'a list'
    if keys:
        expected += ' or an object with one of the keys ' + ', '.join(keys)
    raise CloudTempleError(
        'Unexpected API response, expected {0}'.format(expected))


class CloudTempleClient:

    def __init__(self, client_id, secret_id, api_url=DEFAULT_API_URL,
                 validate_certs=True, timeout=30, max_retries=3,
                 page_size=PAGE_SIZE, sleep=time.sleep):
        self.client_id = client_id
        self.secret_id = secret_id
        self.api_url = api_url.rstrip('/')
        self.validate_certs = validate_certs
        self.timeout = timeout
        self.max_retries = max_retries
        self.page_size = page_size
        self._sleep = sleep
        self._token = None

    def _authenticate(self):
        # The endpoint answers with the raw JWT, not a JSON document.
        token = self._request(
            'POST', AUTH_PATH,
            data={'id': self.client_id, 'secret': self.secret_id},
            auth=False, raw=True)
        token = token.strip().strip('"')
        if not token:
            raise CloudTempleError('Authentication returned an empty token')
        self._token = token

    def _retry_delay(self, error, attempt):
        retry_after = error.headers.get('Retry-After') if error.headers else None
        if retry_after:
            try:
                return min(float(retry_after), 30.0)
            except ValueError:
                pass
        return min(0.5 * 2 ** attempt, 5.0)

    def _request(self, method, path, params=None, data=None, auth=True,
                 raw=False):
        url = self.api_url + path
        if params:
            url += '?' + urlencode(params)
        headers = {'Accept': 'application/json'}
        payload = None
        if data is not None:
            payload = json.dumps(data)
            headers['Content-Type'] = 'application/json'

        attempt = 0
        reauthenticated = False
        while True:
            if auth:
                if self._token is None:
                    self._authenticate()
                headers['Authorization'] = 'Bearer ' + self._token
            try:
                response = open_url(
                    url, method=method, data=payload, headers=headers,
                    validate_certs=self.validate_certs, timeout=self.timeout,
                    http_agent=USER_AGENT)
                text = to_text(response.read())
                break
            except HTTPError as e:
                if e.code == 401 and auth and not reauthenticated:
                    self._token = None
                    reauthenticated = True
                    continue
                if e.code in RETRY_STATUSES and attempt < self.max_retries:
                    self._sleep(self._retry_delay(e, attempt))
                    attempt += 1
                    continue
                try:
                    body = to_text(e.read())[:500]
                except Exception:
                    body = ''
                raise CloudTempleError(
                    '{0} {1} failed with HTTP {2}: {3}'.format(
                        method, path, e.code, body or e.reason),
                    status=e.code)
            except SSLValidationError as e:
                raise CloudTempleError(
                    '{0} {1} failed: {2}'.format(method, path, e))
            except (URLError, OSError, UrlsConnectionError) as e:
                # connection refused, DNS failure, read timeout, TLS error...
                if attempt < self.max_retries:
                    self._sleep(min(0.5 * 2 ** attempt, 5.0))
                    attempt += 1
                    continue
                raise CloudTempleError('{0} {1} failed: {2}'.format(
                    method, path, getattr(e, 'reason', None) or e))

        if raw:
            return text
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            raise CloudTempleError(
                '{0} {1} returned invalid JSON'.format(method, path))

    def list_virtual_machines(self, filters=None):
        vms = []
        seen = set()
        offset = 0
        while True:
            params = dict(filters or {})
            params.update(limit=self.page_size, offset=offset)
            items, total = _unwrap(
                self._request('GET', VMS_PATH, params=params), 'vms')
            new = [vm for vm in items if vm.get('id') not in seen]
            if items and not new:
                # Fail closed if the API ignores the offset instead of
                # looping forever or silently truncating the inventory.
                raise CloudTempleError(
                    'Virtual machine listing made no progress at offset {0}'
                    .format(offset))
            for vm in new:
                seen.add(vm.get('id'))
                vms.append(vm)
            offset += len(items)
            if len(items) < self.page_size or (
                    total is not None and len(vms) >= total):
                return vms

    def list_network_adapters(self, vm_id):
        items, dummy = _unwrap(
            self._request('GET', '{0}/{1}/network_adapters'.format(
                VMS_PATH, vm_id)),
            'networks')
        return items

    def list_floating_ips(self):
        # A bare list on the live API, as documented by the VPC OpenAPI spec
        items, dummy = _unwrap(self._request('GET', FLOATING_IPS_PATH))
        return items
