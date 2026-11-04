# -*- coding: utf-8 -*-

# Copyright (c) 2026, Ahmed Boukerram
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

import pytest

from conftest import CLIENT_ID, SECRET_ID

from ansible_collections.boukerramahmed.cloudtemple.plugins.module_utils.cloudtemple import (
    CloudTempleClient,
    CloudTempleError,
    _unwrap,
)


def make_client(api, **kwargs):
    kwargs.setdefault('sleep', lambda seconds: None)
    return CloudTempleClient(CLIENT_ID, SECRET_ID, api_url=api.url, **kwargs)


def test_lists_all_vms_and_authenticates_once(fake_api):
    client = make_client(fake_api)
    vms = client.list_virtual_machines()
    assert len(vms) == 8
    assert fake_api.tokens_issued == 1


def test_paginates_with_limit_and_offset(fake_api):
    client = make_client(fake_api, page_size=3)
    vms = client.list_virtual_machines()
    assert [vm['id'] for vm in vms] == [vm['id'] for vm in fake_api.vms]
    offsets = [q['offset'][0] for m, p, q in fake_api.requests
               if p.endswith('/virtual_machines')]
    assert offsets == ['0', '3', '6']


def test_fails_when_api_ignores_offset(fake_api):
    fake_api.get_original = fake_api.get

    def same_page(path, query, token):
        query = dict(query, offset=['0'])
        return fake_api.get_original(path, query, token)
    fake_api.get = same_page
    client = make_client(fake_api, page_size=3)
    with pytest.raises(CloudTempleError, match='no progress'):
        client.list_virtual_machines()


def test_passes_filters(fake_api):
    client = make_client(fake_api)
    fake_api.vms[0]['status'] = 'stopped'
    vms = client.list_virtual_machines({'status': 'stopped'})
    assert [vm['name'] for vm in vms] == ['k8s-worker2']


def test_reauthenticates_once_on_expired_token(fake_api):
    client = make_client(fake_api)
    client.list_virtual_machines()
    fake_api.valid_token = 'rotated'
    assert len(client.list_virtual_machines()) == 8
    assert fake_api.tokens_issued == 2


def test_retries_on_429_and_5xx(fake_api):
    delays = []
    client = make_client(fake_api, sleep=delays.append)
    fake_api.failures = [429, 503]
    assert len(client.list_virtual_machines()) == 8
    assert delays == [0.0, 1.0]


def test_gives_up_after_max_retries(fake_api):
    client = make_client(fake_api, max_retries=2)
    fake_api.failures = [503, 503, 503]
    with pytest.raises(CloudTempleError) as e:
        client.list_virtual_machines()
    assert e.value.status == 503


def test_bad_credentials_raise_without_leaking_secret(fake_api):
    client = CloudTempleClient(CLIENT_ID, 'wrong-secret', api_url=fake_api.url)
    with pytest.raises(CloudTempleError) as e:
        client.list_virtual_machines()
    assert e.value.status == 401
    assert 'wrong-secret' not in str(e.value)


def test_network_adapters_and_floating_ips(fake_api):
    client = make_client(fake_api)
    nics = client.list_network_adapters('12622af4-739b-5581-9832-d02b7d53ce7e')
    assert nics[0]['ipv4Address'] == '10.0.0.11'
    assert len(client.list_floating_ips()) == 3


@pytest.mark.parametrize('payload,expected', [
    ([{'id': 1}], ([{'id': 1}], None)),
    ({'vms': [{'id': 1}], 'total': 1}, ([{'id': 1}], 1)),
    (None, ([], None)),
])
def test_unwrap(payload, expected):
    assert _unwrap(payload, 'vms') == expected


def test_unwrap_rejects_unknown_shape():
    with pytest.raises(CloudTempleError):
        _unwrap({'unexpected': 1}, 'vms')


def test_connection_errors_are_retried_then_wrapped():
    delays = []
    # nothing listens on port 9 of localhost: connection refused
    client = CloudTempleClient(CLIENT_ID, SECRET_ID,
                               api_url='http://127.0.0.1:9/api',
                               sleep=delays.append, max_retries=2)
    with pytest.raises(CloudTempleError, match='failed'):
        client.list_virtual_machines()
    assert delays == [0.5, 1.0]
