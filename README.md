# Ansible Collection: `boukerramahmed.cloudtemple`

[![CI](https://github.com/boukerramAhmed/ansible-collection-cloudtemple/actions/workflows/ci.yml/badge.svg)](https://github.com/boukerramAhmed/ansible-collection-cloudtemple/actions/workflows/ci.yml)
[![Ansible Galaxy](https://img.shields.io/badge/galaxy-boukerramahmed.cloudtemple-blue.svg)](https://galaxy.ansible.com/ui/repo/published/boukerramahmed/cloudtemple/)
[![License: GPL v3+](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](LICENSE)

Dynamic inventory for the virtual machines of **[Cloud Temple](https://www.cloud-temple.com/)**
**VM Instances**, the French SecNumCloud-qualified cloud.

The plugin reads your virtual machines from the Cloud Temple API and turns them into Ansible
hosts and groups. You no longer keep a static inventory or a Terraform state reader in sync
with your tenant. Its design follows the
[`openstack.cloud.openstack`](https://github.com/openstack/ansible-collections-openstack)
inventory plugin, including its `meta-app_<app>` groups. If your playbooks already target
OpenStack groups, they work here with few changes.

> This project is a community collection. It is not affiliated with, endorsed by or supported
> by Cloud Temple.

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Configuration reference](#configuration-reference)
- [Hosts and host variables](#hosts-and-host-variables)
- [Groups](#groups)
- [Examples](#examples)
- [Running in CI](#running-in-ci)
- [Reliability and API usage](#reliability-and-api-usage)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [Contributing](#contributing)
- [License](#license)

## Features

- **All the VMs of a tenant**, read from the VM Instances API. The listing is paginated and
  can be filtered by name, status, availability zone or instance family.
- **The right connection address.** By default `ansible_host` is the VM's floating (public) IP,
  matched through the VPC API, and falls back to its private IP. Set `private: true` when
  Ansible runs inside the VPC or through a VPN. IPv6 link-local addresses are ignored.
- **OpenStack-style groups.** Each VM joins `meta-app_<app>`, where `<app>` comes from its
  name: `consul1` joins `meta-app_consul`.
- **Automatic groups** by availability zone, instance family, image, status, network and backup
  policy.
- **Standard Ansible inventory features**: `compose`, `groups`, `keyed_groups`, `strict` and the
  inventory cache.
- **Robust**:
  - JWT renewal;
  - retries with exponential backoff on HTTP 429, 5xx and network errors (`Retry-After` is
    honoured);
  - API errors fail loudly by default instead of producing an empty inventory;
  - a partial result is never cached.
- **No Python dependency** beyond `ansible-core`. The plugin uses only the standard library and
  `ansible.module_utils.urls`.

## Requirements

| Component | Version |
|---|---|
| ansible-core | >= 2.15 (tested with 2.15 to 2.21) |
| Python on the controller | the versions supported by your ansible-core (>= 3.9) |
| Cloud Temple | a tenant using the **VM Instances** product, and a Personal Access Token with read access on VM Instances and VPC (see [Quick start](#quick-start)) |

Nothing is needed on the managed hosts: inventory plugins run on the controller only.

## Installation

From Ansible Galaxy:

```bash
ansible-galaxy collection install boukerramahmed.cloudtemple
```

With a `requirements.yml` file:

```yaml
collections:
  - name: boukerramahmed.cloudtemple
    version: ">=0.1.0"
```

```bash
ansible-galaxy collection install -r requirements.yml
```

From the Git repository, for an unreleased version:

```bash
ansible-galaxy collection install git+https://github.com/boukerramAhmed/ansible-collection-cloudtemple.git,main
```

## Quick start

**1. Create a Personal Access Token (PAT).** In the Cloud Temple console, open your profile,
then *Personal access tokens*. Create a token on the tenant you want to inventory.
- Permissions: read access on *VM Instances* **and** on *VPC*. With the default settings the
  plugin reads floating IPs from the VPC API, and fails if it is not allowed to. If your PAT
  only reads VM Instances, set `private: true` or `fetch_floating_ips: false`.
- Expiry: a PAT expires after at most 12 months.
- Write down the **client ID** and the **secret ID**: the secret is only shown once.

**2. Export the credentials:**

```bash
export CLOUDTEMPLE_CLIENT_ID='<client id>'
export CLOUDTEMPLE_SECRET_ID='<secret id>'
```

**3. Create the inventory file.** Its name **must end with `cloudtemple.yml` or
`cloudtemple.yaml`**, for example `inventory/cloudtemple.yml`:

```yaml
plugin: boukerramahmed.cloudtemple.dynamicinventory
```

**4. Enable the plugin** if your `ansible.cfg` restricts inventory plugins. The default `auto`
plugin loads it without any change.

```ini
[inventory]
enable_plugins = boukerramahmed.cloudtemple.dynamicinventory, yaml, ini
```

**5. Use it:**

```bash
ansible-inventory -i inventory/cloudtemple.yml --graph
ansible -i inventory/cloudtemple.yml all -m ansible.builtin.ping
```

```text
@all:
  |--@ungrouped:
  |  |--reporting-legacy
  |--@meta-app_web:
  |  |--web1
  |--@meta-app_consul:
  |  |--consul1
  |--@meta-app_k8s-worker:
  |  |--k8s-worker1
  |  |--k8s-worker2
  ...
```

Full plugin documentation is also available offline:

```bash
ansible-doc -t inventory boukerramahmed.cloudtemple.dynamicinventory
```

## Configuration reference

| Option | Type | Default | Description |
|---|---|---|---|
| `plugin` | str | *required* | Must be `boukerramahmed.cloudtemple.dynamicinventory`. |
| `api_url` | str | `https://shiva.cloud-temple.com/api` | Base URL of the API. Env: `CLOUDTEMPLE_API_URL`. |
| `client_id` | str | | PAT client ID. Env: `CLOUDTEMPLE_CLIENT_ID` (preferred over the file). |
| `secret_id` | str | | PAT secret ID. Env: `CLOUDTEMPLE_SECRET_ID` (preferred over the file). |
| `validate_certs` | bool | `true` | Validate the TLS certificate of the API. |
| `timeout` | int | `30` | Timeout of each API request, in seconds. |
| `vm_filters` | dict | `{}` | Filters passed to the VM listing: `name`, `status`, `availabilityZoneId`, `familyId`. |
| `fetch_network_adapters` | bool | `true` | Fetch the network adapters of each VM (one request per VM). Without it, no IP is known. |
| `fetch_floating_ips` | bool | `true` | Fetch floating IPs from the VPC API (one request). A failure follows `fail_on_errors`, or only warns with `private: true`. |
| `fail_on_errors` | bool | `true` | Fail when an API request fails. When `false`, the inventory returns what it could fetch (never cached). |
| `inventory_hostname` | str | `name` | `name` (the VM ID is used when names collide) or `uuid`. |
| `private` | bool | `false` | Use the private IP even when a floating IP is attached. |
| `only_ipv4` | bool | `false` | Only use IPv4 addresses for `ansible_host`. |
| `use_names` | bool | `false` | Use the VM name as `ansible_host` (for resolvable FQDNs). |
| `show_all` | bool | `false` | Keep the VMs for which no `ansible_host` can be determined. |
| `auto_groups` | bool | `true` | Create the `cloudtemple`, `az_*`, `family_*`, `image_*`, `status_*`, `network_*` and `backup_policy_*` groups. |
| `app_name_regex` | str | `^(.+?)-?\d+$` | Its first capture group, applied to the VM name, is the VM's *app*. |
| `app_groups` | bool | `true` | Add each VM to `meta-app_<app>`. |
| `compose`, `groups`, `keyed_groups`, `strict`, `leading_separator`, `use_extra_vars` | | | Standard [constructed](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/constructed_inventory.html) options. |
| `cache`, `cache_plugin`, `cache_timeout`, `cache_connection`, `cache_prefix` | | | Standard [inventory cache](https://docs.ansible.com/ansible/latest/plugins/cache.html) options. |

## Hosts and host variables

**Inventory hostname.** By default this is the VM name. If two VMs share a name, both are
registered under their IDs instead. With `inventory_hostname: uuid`, the VM ID is always used.

**`ansible_host`** is chosen in this order:

1. with `use_names: true`, the VM name;
2. otherwise the floating IP bound to one of the VM's private IPs, unless `private: true`;
3. otherwise the first private IP: IPv4 first, adapters ordered by `deviceIndex`.

A floating IP is matched to a VM when its `staticIp.address` equals one of the VM's private
IPv4 addresses on the same private network (`privateNetwork.id` == adapter `networkId`).
This keeps the match correct when several VPCs reuse the same private range.

A VM without any address is skipped, unless `show_all: true` or `use_names: true` is set.

**`cloudtemple`** holds everything the API returns for the VM, plus five keys added by the
plugin: `network_adapters`, `floating_ips`, `private_ips`, `public_ips` and `app`.

```yaml
cloudtemple:
  id: 12622af4-739b-5581-9832-d02b7d53ce7e
  name: web1
  status: running
  app: web                        # from app_name_regex
  az: {id: 05ac3ef0-..., name: fr1-az05}
  image: {id: 4e577ce1-..., name: Ubuntu 24.04 LTS}
  instanceFamily: {id: 7a337968-..., name: Development}
  vcpu: 2
  ramGb: 4
  disksSizeGb: 32
  backupPolicy: {name: No Backup, ...}
  guestToolsInstalled: true
  private_ips: [10.0.0.11]
  public_ips: [198.51.100.61]
  network_adapters:
    - {deviceIndex: 0, networkName: demo-private-network, type: vpc,
       ipv4Addresses: [10.0.0.11], macAddress: '02:00:00:00:00:01', ...}
  floating_ips:
    - {ipAddress: 198.51.100.61, staticIp: {address: 10.0.0.11}, vpc: {name: demo-vpc}, ...}
```

Use `compose` to turn these values into the variables your playbooks expect:

```yaml
compose:
  ansible_user: "'ubuntu'"
  private_ip: cloudtemple.private_ips[0]
  public_ip: cloudtemple.public_ips | first | default('')
```

## Groups

### `meta-app_<app>`: the OpenStack pattern

`openstack.cloud.openstack` puts every server with the metadata `app=<value>` into the group
`meta-app_<value>`. Cloud Temple VM Instances have no metadata or tags, so the *app* comes from
a naming convention instead. `app_name_regex` is applied to the VM name and its first capture
group is the app. The default strips the trailing number:

| VM name | `cloudtemple.app` | Group |
|---|---|---|
| `consul1` | `consul` | `meta-app_consul` |
| `k8s-worker2` | `k8s-worker` | `meta-app_k8s-worker` |
| `web-01` | `web` | `meta-app_web` |
| `reporting-legacy` | `null` | none (still in `all`) |

To migrate playbooks written for OpenStack:
- give your VMs `<app><n>` names in Terraform;
- keep your `group_vars/meta-app_<app>.yml` files and your `hosts: meta-app_<app>` plays.

Group names keep the `-` character, exactly like OpenStack's. To silence Ansible's warning
about it, add this to `ansible.cfg`:

```ini
[defaults]
force_valid_group_names = ignore
```

### Automatic groups

With `auto_groups: true` (the default), each VM also joins:

| Group | Example |
|---|---|
| `cloudtemple` | every VM |
| `az_<availability zone>` | `az_fr1_az05` |
| `family_<instance family>` | `family_development` |
| `image_<image>` | `image_ubuntu_24_04_lts` |
| `status_<status>` | `status_running` |
| `network_<network>` | `network_demo_private_network` |
| `backup_policy_<policy>` | `backup_policy_no_backup` |

These names are lower case. Any character other than a letter, a digit or `_` is replaced by
`_`. Set `auto_groups: false` if you only want the `meta-app_*` groups.

### Your own groups

Every value under `cloudtemple` can drive `groups` and `keyed_groups`:

```yaml
groups:
  kube_control_plane: cloudtemple.app == 'k8s-master'
  kube_node: cloudtemple.app == 'k8s-worker'
  big_vms: cloudtemple.ramGb >= 16
keyed_groups:
  - key: cloudtemple.az.name
    prefix: zone
```

## Examples

The [`examples/`](examples/) directory holds ready-to-use configurations. Each one is tested
in CI against a fake API.

| File | Use case |
|---|---|
| [`minimal.cloudtemple.yml`](examples/minimal.cloudtemple.yml) | Smallest working configuration |
| [`vpn.cloudtemple.yml`](examples/vpn.cloudtemple.yml) | Ansible inside the VPC or through a VPN: private IPs, only `meta-app_*` groups |
| [`ci.cloudtemple.yml`](examples/ci.cloudtemple.yml) | CI runner on the Internet: floating IPs, running VMs only |
| [`kubespray.cloudtemple.yml`](examples/kubespray.cloudtemple.yml) | Groups and variables expected by Kubespray |
| [`cache.cloudtemple.yml`](examples/cache.cloudtemple.yml) | Inventory cache to save API calls |

## Running in CI

- Store the PAT client ID and secret ID as CI secrets and expose them as
  `CLOUDTEMPLE_CLIENT_ID` and `CLOUDTEMPLE_SECRET_ID`.
- **Set `ANSIBLE_INVENTORY_UNPARSED_FAILED=true`.** Even with `fail_on_errors: true`, Ansible
  only *warns* when an inventory source fails to parse, then runs the playbook against an empty
  inventory. This variable makes the job fail instead.
- A runner outside the VPC needs floating IPs. Keep `private: false` and give the PAT read access
  on the VPC API.

```yaml
# GitLab CI example
deploy:
  image: python:3.12
  variables:
    ANSIBLE_INVENTORY_UNPARSED_FAILED: "true"
  script:
    - pip install ansible-core
    - ansible-galaxy collection install boukerramahmed.cloudtemple
    - ansible-playbook -i inventory/cloudtemple.yml site.yml
```

## Reliability and API usage

The plugin makes these requests on each run that misses the cache, where *n* is the number of
VMs:

| Request | Count |
|---|---|
| `POST /iam/v2/auth/personal_access_token` | 1, plus 1 per renewal |
| `GET /vm_instances/v1/virtual_machines` (200 per page) | ⌈n / 200⌉ |
| `GET /vm_instances/v1/virtual_machines/{id}/network_adapters` | n (unless `fetch_network_adapters: false`) |
| `GET /vpc/v1/floating_ips` | 1 (unless `fetch_floating_ips: false`) |

Behaviour on errors:

- **Token expiry.** The JWT is valid for 5 minutes. On a `401`, the plugin authenticates again
  once and replays the request.
- **Rate limits and transient failures.** On `429`, `5xx` and network errors, the request is
  retried 3 times with exponential backoff (0.5 s, 1 s, 2 s, capped at 5 s). `Retry-After` is
  honoured when present. The API allows 25 requests per second per source IP.
- **Pagination safety.** If the API ignores `offset` and returns the same page again, the
  plugin fails instead of looping or silently truncating the inventory.
- **Errors.** With `fail_on_errors: true` (the default), any API error fails the inventory.
  With `false`, the plugin warns and returns what it could fetch. That partial result is never
  written to the cache.

For large tenants, enable the [cache](examples/cache.cloudtemple.yml) to avoid one adapter
request per VM on every run.

## Security

- Use a **read-only** PAT, limited to the tenant you inventory.
- Pass credentials through environment variables or your CI secret store rather than writing
  them in the inventory file.
- The plugin never logs the secret or the JWT. Neither is written to the cache: the cache holds
  only the VM data returned by the API.
- `validate_certs` defaults to `true`. Only disable it to test against a local API.

See [SECURITY.md](SECURITY.md) to report a vulnerability.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Unable to parse ... as an inventory source` and no host | Ansible did not use the plugin. Check that the file name ends with `cloudtemple.yml`, that the collection is installed (`ansible-galaxy collection list`), and that the plugin is listed in `enable_plugins` if you restrict it. Run with `-vvv` to see why each plugin skipped the file. |
| `Cloud Temple credentials are missing` | `CLOUDTEMPLE_CLIENT_ID` or `CLOUDTEMPLE_SECRET_ID` is not set in the environment of `ansible-inventory`. |
| `... failed with HTTP 401` | Wrong or expired PAT. Tokens expire after at most 12 months. |
| `Fetching Cloud Temple floating IPs failed with: ... HTTP 403` | The PAT cannot read the VPC API. Grant it VPC read access, set `private: true`, or set `fetch_floating_ips: false`. |
| A VM is missing | It has no IP address yet (still provisioning). Use `show_all: true` to list it anyway. |
| A VM has no `meta-app_*` group | Its name does not match `app_name_regex`; by default the name must end with a number. |
| Warning about invalid characters in group names | Set `force_valid_group_names = ignore` in `ansible.cfg` (see [Groups](#groups)). |
| Stale hosts | The inventory cache is enabled. Run `ansible-inventory --flush-cache` or lower `cache_timeout`. |

Run `ansible-inventory -i cloudtemple.yml --list -vvvv` for the details of every API call
that failed.

## Limitations

- Only the **VM Instances** product is supported. IaaS VMware, IaaS OpenSource and bare metal
  are not.
- One plugin configuration reads one tenant, because a PAT belongs to a single tenant. To
  inventory several tenants, use one file per tenant with its own `client_id` and `secret_id`.
- The VM Instances API exposes no tags or metadata, so the app groups rely on VM names.
- The public OpenAPI specification documents the VM listing as a bare array, but the live API
  returns `{"vms": [...], "total": N}`. The plugin accepts both.

## Contributing

Contributions are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup,
tests and release process. Everyone taking part is expected to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

Changes are listed in [CHANGELOG.md](CHANGELOG.md).

## License

GNU General Public License v3.0 or later. See [LICENSE](LICENSE).

The design of the inventory plugin is inspired by the OpenStack inventory plugin of
[`openstack.cloud`](https://github.com/openstack/ansible-collections-openstack), also licensed
under GPL-3.0-or-later.
