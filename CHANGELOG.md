# Changelog

All notable changes to the `boukerramahmed.cloudtemple` collection are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
collection follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html): breaking
changes to options, host variables or group names bump the major version.

## [Unreleased]

## [0.1.0] - Unreleased

First public release.

### Added

- Inventory plugin `boukerramahmed.cloudtemple.dynamicinventory` for Cloud Temple VM Instances.
- Authentication with a Personal Access Token (`CLOUDTEMPLE_CLIENT_ID` /
  `CLOUDTEMPLE_SECRET_ID`), with automatic renewal of the JWT on `401`.
- Paginated VM listing with `vm_filters` (`name`, `status`, `availabilityZoneId`, `familyId`).
- IP addresses from the network adapters of each VM, ignoring IPv6 link-local addresses.
- Floating IPs from the VPC API, matched to the private IP on the same private network.
- `ansible_host` selection: floating IP, then private IP. Options `private`, `only_ipv4` and
  `use_names` change the choice.
- Host variable `cloudtemple` with the API data, plus `network_adapters`, `floating_ips`,
  `private_ips`, `public_ips` and `app`.
- OpenStack-style `meta-app_<app>` groups, the app being derived from the VM name
  (`app_name_regex`, `app_groups`).
- Automatic groups by availability zone, instance family, image, status, network and backup
  policy (`auto_groups`).
- Constructed features (`compose`, `groups`, `keyed_groups`) and the inventory cache.
- Retries with exponential backoff on `429`, `5xx` and network errors, honouring `Retry-After`.
- `fail_on_errors` (default `true`); a partial result is never written to the cache.

[Unreleased]: https://github.com/boukerramAhmed/ansible-collection-cloudtemple/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/boukerramAhmed/ansible-collection-cloudtemple/releases/tag/v0.1.0
