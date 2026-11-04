# -*- coding: utf-8 -*-

# Copyright (c) 2026, Ahmed Boukerram
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
name: dynamicinventory
author: Ahmed Boukerram (@boukerramAhmed)
short_description: Cloud Temple VM Instances inventory source
description:
  - Gather virtual machines from the Cloud Temple VM Instances API and add
    them as Ansible hosts to your inventory.
  - Use a YAML configuration file whose name ends with C(cloudtemple.yml) or
    C(cloudtemple.yaml) to configure this inventory plugin.
  - Authenticates with a Personal Access Token (PAT) of a single tenant. A
    read-only PAT is enough.
  - All data returned by the API for a server is exposed in the host variable
    C(cloudtemple).
options:
  plugin:
    description:
      - Token which marks a given YAML configuration file as a valid input file
        for this inventory plugin.
    required: true
    choices: ['boukerramahmed.cloudtemple.dynamicinventory']
  api_url:
    description:
      - Base URL of the Cloud Temple API.
    type: str
    default: https://shiva.cloud-temple.com/api
    env:
      - name: CLOUDTEMPLE_API_URL
  client_id:
    description:
      - Client ID of the Personal Access Token.
      - Prefer the environment variable over writing it in the file.
    type: str
    env:
      - name: CLOUDTEMPLE_CLIENT_ID
  secret_id:
    description:
      - Secret ID of the Personal Access Token.
      - Prefer the environment variable over writing it in the file.
    type: str
    env:
      - name: CLOUDTEMPLE_SECRET_ID
  validate_certs:
    description:
      - Whether to validate the TLS certificate of the API.
    type: bool
    default: true
  timeout:
    description:
      - Timeout in seconds of each API request.
    type: int
    default: 30
  vm_filters:
    description:
      - Filters passed as is to C(GET /vm_instances/v1/virtual_machines).
      - Supported keys are C(name), C(status), C(availabilityZoneId) and
        C(familyId).
    type: dict
    default: {}
  fetch_network_adapters:
    description:
      - Query the network adapters of every virtual machine to learn its IP
        addresses. This is one API request per virtual machine.
      - Without it no IP address is known and I(ansible_host) is only set
        when I(use_names) is C(true).
    type: bool
    default: true
  fetch_floating_ips:
    description:
      - Query the VPC API for floating (public) IP addresses and attach them
        to the virtual machines owning the matching private IP.
      - A failure of this request, for example because the PAT has no VPC
        permission, follows I(fail_on_errors), since I(ansible_host) would
        silently fall back to private IPs. With I(private=true) it only
        emits a warning.
    type: bool
    default: true
  fail_on_errors:
    description:
      - Whether the inventory fails when an API request fails, for example
        due to bad credentials or connectivity issues.
      - When C(false), the inventory returns the hosts it could fetch on a
        best effort basis. Such an incomplete result is never written to
        the inventory cache.
    type: bool
    default: true
  inventory_hostname:
    description:
      - What to register as inventory hostname.
      - When set to C(name) the name of a virtual machine is used. When
        several virtual machines share the same name, their IDs are used.
      - When set to C(uuid) the ID of a virtual machine is used.
    type: str
    choices: ['name', 'uuid']
    default: name
  private:
    description:
      - Use private IP addresses even when a floating IP address is attached.
      - Useful when Ansible runs inside the VPC or through a VPN.
    type: bool
    default: false
  only_ipv4:
    description:
      - Use only IPv4 addresses for I(ansible_host). Link-local IPv6
        addresses are always ignored.
    type: bool
    default: false
  use_names:
    description:
      - Use the virtual machine name as I(ansible_host) instead of an IP
        address. Useful when names are resolvable FQDNs.
    type: bool
    default: false
  show_all:
    description:
      - Whether all virtual machines are listed.
      - When C(false), virtual machines for which no I(ansible_host) can be
        determined (no IP address and I(use_names) disabled) are skipped.
    type: bool
    default: false
  auto_groups:
    description:
      - Automatically create groups C(cloudtemple), C(az_<name>),
        C(family_<name>), C(image_<name>), C(status_<status>),
        C(network_<name>) and C(backup_policy_<name>).
      - Group names are lower case, any character other than a letter, a
        digit or an underscore is replaced by an underscore.
    type: bool
    default: true
  app_name_regex:
    description:
      - Regular expression applied to the virtual machine name, its first
        capture group is the application name of the virtual machine, exposed
        as C(cloudtemple.app).
      - Cloud Temple VM Instances have no metadata, the application name
        comes from a naming convention instead of the C(app) metadata of
        OpenStack servers.
      - The default strips the trailing number, C(consul1) gives C(consul)
        and C(k8s-worker2) gives C(k8s-worker).
      - C(cloudtemple.app) is C(null) when the name does not match.
    type: str
    default: '^(.+?)-?\d+$'
  app_groups:
    description:
      - Add every virtual machine having an application name to the group
        C(meta-app_<app>), the group created by C(openstack.cloud.openstack)
        for the server metadata C(app=<app>).
      - The group name is used as is. Set C(force_valid_group_names = ignore)
        in C(ansible.cfg) to silence the warning about the C(-) character.
    type: bool
    default: true
requirements:
  - "python >= 3.9"
extends_documentation_fragment:
  - inventory_cache
  - constructed
'''

EXAMPLES = r'''
# Create a file called cloudtemple.yml, add the following content and run
# $> export CLOUDTEMPLE_CLIENT_ID=... CLOUDTEMPLE_SECRET_ID=...
# $> ansible-inventory -i cloudtemple.yml --graph
plugin: boukerramahmed.cloudtemple.dynamicinventory

# Only running virtual machines
vm_filters:
  status: running

# Connect through private IPs (e.g. from the OpenVPN)
private: true

keyed_groups:
  - key: cloudtemple.az.name
    prefix: zone
compose:
  ansible_user: "'ubuntu'"
'''

import collections
import ipaddress
import re

from ansible.errors import AnsibleParserError
from ansible.plugins.inventory import BaseInventoryPlugin, Constructable, Cacheable

from ansible_collections.boukerramahmed.cloudtemple.plugins.module_utils.cloudtemple import (
    CloudTempleClient,
    CloudTempleError,
)


def _is_link_local(address):
    try:
        return ipaddress.ip_address(address).is_link_local
    except ValueError:
        return False


class InventoryModule(BaseInventoryPlugin, Constructable, Cacheable):

    NAME = 'boukerramahmed.cloudtemple.dynamicinventory'

    def verify_file(self, path):
        if super(InventoryModule, self).verify_file(path):
            return path.endswith(('cloudtemple.yml', 'cloudtemple.yaml'))
        return False

    def parse(self, inventory, loader, path, cache=True):

        super(InventoryModule, self).parse(inventory, loader, path,
                                           cache=cache)

        self._read_config_data(path)

        servers = self._fetch_servers(path, cache)

        # determine inventory hostnames
        if self.get_option('inventory_hostname') == 'name':
            count = collections.Counter(s['name'] for s in servers)
            inventory = dict(((server['name'], server)
                              if count[server['name']] == 1
                              else (server['id'], server))
                             for server in servers)
        else:  # self.get_option('inventory_hostname') == 'uuid'
            inventory = dict((server['id'], server) for server in servers)

        for hostname, server in inventory.items():
            host_vars = self._generate_host_vars(server)
            if 'ansible_host' not in host_vars and not self.get_option('show_all'):
                self.display.vvv(
                    'Skipping {0} which has no address'.format(hostname))
                continue
            self._add_host(hostname, host_vars)
            if self.get_option('auto_groups'):
                for group in self._generate_auto_groups(server):
                    self.inventory.add_group(group)
                    self.inventory.add_child(group, hostname)
            app = host_vars['cloudtemple']['app']
            if self.get_option('app_groups') and app:
                group = self.inventory.add_group('meta-app_{0}'.format(app))
                self.inventory.add_child(group, hostname)

    def _add_host(self, hostname, host_vars):
        self.inventory.add_host(hostname, group='all')

        for k, v in host_vars.items():
            self.inventory.set_variable(hostname, k, v)

        strict = self.get_option('strict')

        self._set_composite_vars(
            self.get_option('compose'), host_vars, hostname, strict=strict)

        self._add_host_to_composed_groups(
            self.get_option('groups'), host_vars, hostname, strict=strict)

        self._add_host_to_keyed_groups(
            self.get_option('keyed_groups'), host_vars, hostname,
            strict=strict)

    def _fetch_servers(self, path, cache):
        cache_key = self.get_cache_key(path)
        user_cache_setting = self.get_option('cache')
        attempt_to_read_cache = user_cache_setting and cache
        cache_needs_update = user_cache_setting and not cache

        servers = None

        if attempt_to_read_cache:
            self.display.vvvv('Reading Cloud Temple inventory cache key {0}'
                              .format(cache_key))
            try:
                servers = self._cache[cache_key]
            except KeyError:
                self.display.vvvv('Cloud Temple inventory cache not found')
                cache_needs_update = True

        self._incomplete = False
        if servers is None:
            servers = self._query_api()

        # Never cache a best effort result: later runs would replay it silently.
        if cache_needs_update and not self._incomplete:
            self._cache[cache_key] = servers

        return servers

    def _fail_or_warn(self, message):
        if self.get_option('fail_on_errors'):
            raise AnsibleParserError(message)
        self._warn_incomplete(message)

    def _warn_incomplete(self, message):
        self._incomplete = True
        self.display.warning(message)

    def _query_api(self):
        client_id = self.get_option('client_id')
        secret_id = self.get_option('secret_id')
        if not client_id or not secret_id:
            raise AnsibleParserError(
                'Cloud Temple credentials are missing, set CLOUDTEMPLE_CLIENT_ID'
                ' and CLOUDTEMPLE_SECRET_ID or the options client_id and'
                ' secret_id')

        client = CloudTempleClient(
            client_id, secret_id,
            api_url=self.get_option('api_url'),
            validate_certs=self.get_option('validate_certs'),
            timeout=self.get_option('timeout'))

        self.display.vvvv('Retrieving virtual machines from Cloud Temple')
        try:
            servers = client.list_virtual_machines(
                self.get_option('vm_filters'))
        except CloudTempleError as e:
            self._fail_or_warn(
                'Fetching Cloud Temple virtual machines failed with: {0}'
                .format(e))
            return []

        for server in servers:
            server['network_adapters'] = []
            if not self.get_option('fetch_network_adapters'):
                continue
            try:
                server['network_adapters'] = sorted(
                    client.list_network_adapters(server['id']),
                    key=lambda nic: nic.get('deviceIndex') or 0)
            except CloudTempleError as e:
                self._fail_or_warn(
                    'Fetching network adapters of {0} failed with: {1}'
                    .format(server['name'], e))

        floating_ips = []
        if self.get_option('fetch_floating_ips'):
            try:
                floating_ips = client.list_floating_ips()
            except CloudTempleError as e:
                message = ('Fetching Cloud Temple floating IPs failed with:'
                           ' {0}'.format(e))
                if self.get_option('private'):
                    # ansible_host does not depend on floating IPs
                    self._warn_incomplete(message)
                else:
                    self._fail_or_warn(message)

        for server in servers:
            server['floating_ips'] = self._match_floating_ips(
                server, floating_ips)

        return servers

    @staticmethod
    def _nic_addresses(nic):
        ipv4 = nic.get('ipv4Addresses') or (
            [nic['ipv4Address']] if nic.get('ipv4Address') else [])
        ipv6 = nic.get('ipv6Addresses') or (
            [nic['ipv6Address']] if nic.get('ipv6Address') else [])
        return ipv4, [a for a in ipv6 if not _is_link_local(a)]

    def _match_floating_ips(self, server, floating_ips):
        by_address = collections.defaultdict(list)
        for fip in floating_ips:
            address = (fip.get('staticIp') or {}).get('address')
            if address:
                by_address[address].append(fip)

        matched = []
        for nic in server['network_adapters']:
            ipv4, dummy = self._nic_addresses(nic)
            for address in ipv4:
                candidates = by_address.get(address, [])
                # A private address can be reused in another VPC, so prefer
                # a floating IP bound to the same private network.
                same_network = [
                    fip for fip in candidates
                    if (fip.get('privateNetwork') or {}).get('id')
                    == nic.get('networkId')]
                if same_network:
                    matched.extend(same_network)
                elif len(candidates) == 1:
                    matched.extend(candidates)
        return matched

    def _generate_host_vars(self, server):
        private_ips = []
        for nic in server['network_adapters']:
            ipv4, ipv6 = self._nic_addresses(nic)
            private_ips.extend(ipv4)
            if not self.get_option('only_ipv4'):
                private_ips.extend(ipv6)
        public_ips = [fip['ipAddress'] for fip in server['floating_ips']
                      if fip.get('ipAddress')]

        match = re.match(self.get_option('app_name_regex'), server['name'])
        app = match.group(1) if match and match.groups() else None

        host_vars = dict(cloudtemple=dict(server, app=app,
                                          private_ips=private_ips,
                                          public_ips=public_ips))

        if self.get_option('use_names'):
            ip = server['name']
        elif public_ips and not self.get_option('private'):
            ip = public_ips[0]
        else:
            ip = private_ips[0] if private_ips else None

        if ip is not None:
            host_vars['ansible_host'] = ip

        return host_vars

    @staticmethod
    def _group_name(prefix, value):
        name = '{0}_{1}'.format(prefix, value).lower()
        return re.sub(r'[^0-9a-z_]+', '_', name).strip('_')

    def _generate_auto_groups(self, server):
        groups = ['cloudtemple']

        for prefix, key in (('az', 'az'),
                            ('family', 'instanceFamily'),
                            ('image', 'image'),
                            ('backup_policy', 'backupPolicy')):
            name = (server.get(key) or {}).get('name')
            if name:
                groups.append(self._group_name(prefix, name))

        if server.get('status'):
            groups.append(self._group_name('status', server['status']))

        for nic in server['network_adapters']:
            if nic.get('networkName'):
                groups.append(self._group_name('network', nic['networkName']))

        return groups
