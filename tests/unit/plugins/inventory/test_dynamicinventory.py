# -*- coding: utf-8 -*-

# Copyright (c) 2026, Ahmed Boukerram
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""End to end tests running ansible-inventory against the fake API."""

import json
import os
import subprocess
import sys

import yaml

from conftest import CLIENT_ID, COLLECTIONS_PATH, ROOT, SECRET_ID

WEB = '12622af4-739b-5581-9832-d02b7d53ce7e'


def untag(value):
    # ansible-core >= 2.19 marks inventory strings as unsafe in --list output
    if isinstance(value, dict):
        if set(value) == {'__ansible_unsafe'}:
            return value['__ansible_unsafe']
        return dict((k, untag(v)) for k, v in value.items())
    if isinstance(value, list):
        return [untag(v) for v in value]
    return value


def run_inventory(api, tmp_path, config=None, env=None, check=True):
    path = tmp_path / 'cloudtemple.yml'
    data = {'plugin': 'boukerramahmed.cloudtemple.dynamicinventory',
            'api_url': api.url}
    data.update(config or {})
    path.write_text(yaml.safe_dump(data))
    return run_inventory_file(path, env=env, check=check)


def run_inventory_file(path, env=None, check=True):
    full_env = dict(os.environ,
                    ANSIBLE_COLLECTIONS_PATH=COLLECTIONS_PATH,
                    ANSIBLE_INVENTORY_UNPARSED_FAILED='true',
                    CLOUDTEMPLE_CLIENT_ID=CLIENT_ID,
                    CLOUDTEMPLE_SECRET_ID=SECRET_ID)
    full_env.update(env or {})
    ansible_inventory = os.path.join(os.path.dirname(sys.executable),
                                     'ansible-inventory')
    result = subprocess.run(
        [ansible_inventory, '-i', str(path), '--list'], cwd=str(path.parent),
        env=full_env, capture_output=True, text=True, check=False)
    if check:
        assert result.returncode == 0, result.stderr
        return untag(json.loads(result.stdout)), result.stderr
    return result


def hostvars(inventory):
    return inventory['_meta']['hostvars']


def test_hosts_and_ansible_host(fake_api, tmp_path):
    inventory, dummy = run_inventory(fake_api, tmp_path)
    hv = hostvars(inventory)
    assert sorted(hv) == sorted(vm['name'] for vm in fake_api.vms)
    # floating IP bound on the same private network wins over the one of
    # another VPC sharing the same private address
    assert hv['web1']['ansible_host'] == '198.51.100.61'
    assert hv['vpn-gateway1']['ansible_host'] == '198.51.100.63'
    assert hv['consul1']['ansible_host'].startswith('10.0.0.')
    ct = hv['web1']['cloudtemple']
    assert ct['id'] == WEB
    assert ct['private_ips'] == ['10.0.0.11']
    assert ct['public_ips'] == ['198.51.100.61']
    assert ct['network_adapters'][0]['networkName'] == 'demo-private-network'


def test_private_option(fake_api, tmp_path):
    inventory, dummy = run_inventory(fake_api, tmp_path, {'private': True})
    assert hostvars(inventory)['web1']['ansible_host'] == '10.0.0.11'


def test_use_names(fake_api, tmp_path):
    inventory, dummy = run_inventory(fake_api, tmp_path, {'use_names': True})
    assert hostvars(inventory)['consul1']['ansible_host'] == 'consul1'


def test_auto_groups(fake_api, tmp_path):
    inventory, dummy = run_inventory(fake_api, tmp_path)
    for group in ('cloudtemple', 'az_fr1_az05', 'family_development',
                  'image_ubuntu_24_04_lts', 'status_running',
                  'network_demo_private_network',
                  'backup_policy_no_backup'):
        assert len(inventory[group]['hosts']) == 8, group


def test_auto_groups_disabled(fake_api, tmp_path):
    inventory, dummy = run_inventory(fake_api, tmp_path, {'auto_groups': False})
    assert 'az_fr1_az05' not in inventory


def test_constructed_features(fake_api, tmp_path):
    inventory, dummy = run_inventory(fake_api, tmp_path, {
        'keyed_groups': [{'key': 'cloudtemple.az.name', 'prefix': 'zone'}],
        'groups': {'k8s': "inventory_hostname.startswith('k8s-')"},
        'compose': {'ansible_user': "'ubuntu'"},
    })
    assert sorted(inventory['k8s']['hosts']) == [
        'k8s-worker1', 'k8s-worker2', 'k8s-worker3']
    assert len(inventory['zone_fr1_az05']['hosts']) == 8
    assert hostvars(inventory)['consul1']['ansible_user'] == 'ubuntu'


def test_duplicate_names_use_ids(fake_api, tmp_path):
    fake_api.vms[1]['name'] = fake_api.vms[0]['name']
    inventory, dummy = run_inventory(fake_api, tmp_path)
    hv = hostvars(inventory)
    assert fake_api.vms[0]['id'] in hv and fake_api.vms[1]['id'] in hv
    assert 'k8s-worker2' not in hv


def test_vm_without_ip_is_skipped_unless_show_all(fake_api, tmp_path):
    fake_api.adapters.pop(WEB)
    inventory, dummy = run_inventory(fake_api, tmp_path)
    assert 'web1' not in hostvars(inventory)
    inventory, dummy = run_inventory(fake_api, tmp_path, {'show_all': True})
    assert 'ansible_host' not in hostvars(inventory)['web1']


def test_floating_ips_forbidden_fails_when_floating_ips_are_used(fake_api,
                                                                 tmp_path):
    # ansible_host would silently become a private IP for a CI outside the VPC
    fake_api.floating_ips_status = 403
    result = run_inventory(fake_api, tmp_path, check=False)
    assert result.returncode != 0
    assert 'floating IPs failed' in result.stderr


def test_floating_ips_forbidden_warns_with_private(fake_api, tmp_path):
    fake_api.floating_ips_status = 403
    inventory, stderr = run_inventory(fake_api, tmp_path, {'private': True})
    assert hostvars(inventory)['web1']['ansible_host'] == '10.0.0.11'
    assert 'floating IPs failed' in stderr


def test_floating_ips_forbidden_best_effort(fake_api, tmp_path):
    fake_api.floating_ips_status = 403
    inventory, stderr = run_inventory(fake_api, tmp_path,
                                      {'fail_on_errors': False})
    assert hostvars(inventory)['web1']['ansible_host'] == '10.0.0.11'
    assert 'floating IPs failed' in stderr


def test_bad_credentials_fail(fake_api, tmp_path):
    result = run_inventory(fake_api, tmp_path,
                           env={'CLOUDTEMPLE_SECRET_ID': 'wrong-secret'},
                           check=False)
    assert result.returncode != 0
    assert 'HTTP 401' in result.stderr
    assert 'wrong-secret' not in result.stderr


def test_missing_credentials_fail(fake_api, tmp_path):
    result = run_inventory(fake_api, tmp_path,
                           env={'CLOUDTEMPLE_CLIENT_ID': ''}, check=False)
    assert result.returncode != 0
    assert 'credentials are missing' in result.stderr


def test_vm_filters(fake_api, tmp_path):
    fake_api.vms[0]['status'] = 'stopped'
    inventory, dummy = run_inventory(fake_api, tmp_path,
                                     {'vm_filters': {'status': 'running'}})
    assert len(hostvars(inventory)) == 7


def test_cache(fake_api, tmp_path):
    config = {'cache': True, 'cache_plugin': 'ansible.builtin.jsonfile',
              'cache_connection': str(tmp_path / 'cache')}
    run_inventory(fake_api, tmp_path, config)
    calls = len(fake_api.requests)
    inventory, dummy = run_inventory(fake_api, tmp_path, config)
    assert len(fake_api.requests) == calls
    assert len(hostvars(inventory)) == 8


def test_best_effort_result_is_not_cached(fake_api, tmp_path):
    config = {'cache': True, 'cache_plugin': 'ansible.builtin.jsonfile',
              'cache_connection': str(tmp_path / 'cache'),
              'fail_on_errors': False}
    # the VM listing fails: empty best effort inventory, with a warning
    fake_api.failures = [400]
    inventory, stderr = run_inventory(fake_api, tmp_path, config)
    assert 'virtual machines failed' in stderr
    assert not hostvars(inventory)
    # the API is back: the empty result was not replayed from the cache
    inventory, dummy = run_inventory(fake_api, tmp_path, config)
    assert len(hostvars(inventory)) == 8


def test_use_names_without_network_adapters(fake_api, tmp_path):
    inventory, dummy = run_inventory(fake_api, tmp_path, {
        'use_names': True, 'fetch_network_adapters': False})
    hv = hostvars(inventory)
    assert len(hv) == 8
    assert hv['consul1']['ansible_host'] == 'consul1'


def test_app_groups_from_names(fake_api, tmp_path):
    inventory, stderr = run_inventory(fake_api, tmp_path)
    assert sorted(inventory['meta-app_k8s-worker']['hosts']) == [
        'k8s-worker1', 'k8s-worker2', 'k8s-worker3']
    assert inventory['meta-app_consul']['hosts'] == ['consul1']
    assert inventory['meta-app_vpn-gateway']['hosts'] == ['vpn-gateway1']
    hv = hostvars(inventory)
    assert hv['k8s-worker1']['cloudtemple']['app'] == 'k8s-worker'
    # no trailing number: no application, no meta-app group
    assert hv['reporting-legacy']['cloudtemple']['app'] is None
    assert not any('reporting' in g for g in inventory)


def test_app_name_regex_usable_in_constructed_groups(fake_api, tmp_path):
    inventory, dummy = run_inventory(fake_api, tmp_path, {
        'app_name_regex': r'^([a-z0-9]+)',
        'groups': {'kube_node': "cloudtemple.app == 'k8s'"},
    })
    assert len(inventory['meta-app_k8s']['hosts']) == 3
    assert len(inventory['kube_node']['hosts']) == 3


def test_app_groups_disabled(fake_api, tmp_path):
    inventory, dummy = run_inventory(fake_api, tmp_path, {'app_groups': False})
    assert not any(g.startswith('meta-app_') for g in inventory)


EXAMPLES = os.path.join(ROOT, 'examples')


def run_example(api, tmp_path, name):
    path = tmp_path / name
    with open(os.path.join(EXAMPLES, name)) as f:
        path.write_text(f.read())
    return run_inventory_file(path, env={'CLOUDTEMPLE_API_URL': api.url})


def test_example_minimal(fake_api, tmp_path):
    inventory, dummy = run_example(fake_api, tmp_path, 'minimal.cloudtemple.yml')
    assert len(hostvars(inventory)) == 8
    assert hostvars(inventory)['web1']['ansible_host'] == '198.51.100.61'


def test_example_vpn(fake_api, tmp_path):
    inventory, dummy = run_example(fake_api, tmp_path, 'vpn.cloudtemple.yml')
    hv = hostvars(inventory)
    assert hv['web1']['ansible_host'] == '10.0.0.11'
    assert hv['web1']['public_ip'] == '198.51.100.61'
    assert hv['consul1']['public_ip'] == ''
    assert inventory['meta-app_web']['hosts'] == ['web1']
    assert 'az_fr1_az05' not in inventory


def test_example_ci(fake_api, tmp_path):
    fake_api.vms[0]['status'] = 'stopped'
    inventory, dummy = run_example(fake_api, tmp_path, 'ci.cloudtemple.yml')
    hv = hostvars(inventory)
    assert len(hv) == 7
    assert hv['web1']['ansible_host'] == '198.51.100.61'
    assert len(inventory['zone_fr1_az05']['hosts']) == 7


def test_example_kubespray(fake_api, tmp_path):
    fake_api.vms[0]['name'] = 'k8s-master1'
    inventory, dummy = run_example(fake_api, tmp_path, 'kubespray.cloudtemple.yml')
    assert inventory['kube_control_plane']['hosts'] == ['k8s-master1']
    assert inventory['etcd']['hosts'] == ['k8s-master1']
    assert sorted(inventory['kube_node']['hosts']) == ['k8s-worker1', 'k8s-worker3']
    assert len(inventory['k8s_cluster']['hosts']) == 3
    assert hostvars(inventory)['k8s-master1']['ip'].startswith('10.0.0.')


def test_example_cache(fake_api, tmp_path):
    run_example(fake_api, tmp_path, 'cache.cloudtemple.yml')
    calls = len(fake_api.requests)
    inventory, dummy = run_example(fake_api, tmp_path, 'cache.cloudtemple.yml')
    assert len(fake_api.requests) == calls
    assert len(hostvars(inventory)) == 8
    assert (tmp_path / '.cache' / 'cloudtemple-inventory').is_dir()
