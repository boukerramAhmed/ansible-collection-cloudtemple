# Contributing

Thank you for your interest in `boukerramahmed.cloudtemple`! Bug reports, documentation fixes,
new options and support for other Cloud Temple products are all welcome.

By taking part in this project you agree to follow its [Code of Conduct](CODE_OF_CONDUCT.md).
Security issues must **not** be reported in public issues: see [SECURITY.md](SECURITY.md).

## Reporting a bug or requesting a feature

Open an issue with the matching template. For a bug, include:

- the output of `ansible --version` and `ansible-galaxy collection list boukerramahmed.cloudtemple`;
- your inventory file, **without credentials**;
- the output of `ansible-inventory -i <file> --list -vvvv`, after removing the IP addresses,
  names and IDs you do not want to publish.

## Development setup

The collection has no dependency besides `ansible-core`. The test suite needs `pytest` and
`PyYAML`.

```bash
git clone https://github.com/boukerramAhmed/ansible-collection-cloudtemple.git
cd ansible-collection-cloudtemple
python3 -m venv .venv
.venv/bin/pip install -r tests/requirements.txt
```

### Layout

```text
plugins/inventory/dynamicinventory.py   the inventory plugin (options, hosts, groups)
plugins/module_utils/cloudtemple.py     the Cloud Temple API client (auth, retries, pagination)
tests/unit/conftest.py                  fake Cloud Temple API served on localhost
tests/unit/fixtures/                    API responses served by the fake API (anonymized)
tests/unit/plugins/                     unit and end-to-end tests
examples/                               documented configurations, all tested
```

## Running the tests

```bash
.venv/bin/pytest
```

The plugin tests run the real `ansible-inventory` command against a fake API started on
`127.0.0.1`. They need neither credentials nor network access. `tests/unit/conftest.py` builds
a temporary `ansible_collections/boukerramahmed/cloudtemple` tree pointing at your checkout,
so the tests run from any directory name.

To test against another ansible-core version:

```bash
python3 -m venv .venv-2.15
.venv-2.15/bin/pip install 'ansible-core~=2.15.0' pytest pyyaml
.venv-2.15/bin/pytest
```

### Sanity tests

`ansible-test` requires the collection to sit in a path ending with
`ansible_collections/boukerramahmed/cloudtemple`:

```bash
mkdir -p /tmp/ac/ansible_collections/boukerramahmed
ln -s "$PWD" /tmp/ac/ansible_collections/boukerramahmed/cloudtemple
cd /tmp/ac/ansible_collections/boukerramahmed/cloudtemple
ansible-test sanity --requirements --python 3.12
```

CI runs the sanity tests on every supported ansible-core version and the unit tests on the
same matrix. A pull request must pass both.

### Testing against a real tenant

Use a read-only Personal Access Token:

```bash
export CLOUDTEMPLE_CLIENT_ID=... CLOUDTEMPLE_SECRET_ID=...
ansible-inventory -i examples/minimal.cloudtemple.yml --graph
```

If you add a fixture from a real tenant, **anonymize it first**. Replace UUIDs, VM, network and
VPC names, MAC addresses and IP addresses (use the documentation ranges `198.51.100.0/24` and
`10.0.0.0/24`).

## Coding guidelines

- Follow the existing style. `ansible-test sanity` enforces PEP 8, pylint, the documentation
  format and the import rules.
- Use only the Python standard library and `ansible.module_utils` in the plugin and the client.
  The collection must keep working with a plain `pip install ansible-core`.
- Document every new option in the plugin's `DOCUMENTATION` block, in the configuration table of
  the [README](README.md) and, when useful, in an example under `examples/`.
- Add a test for every behaviour change. Most plugin tests are end to end: configure the
  `fake_api` fixture, run `run_inventory()` and check the hosts, groups and variables.
- Never log or cache credentials or tokens.
- Keep the plugin backward compatible. Renaming or removing an option, a host variable or a
  group name is a breaking change.

## Submitting a pull request

1. Fork the repository and create a branch from `main`.
2. Make your change with its tests and documentation.
3. Add a line under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md), in the `Added`,
   `Changed`, `Fixed` or `Removed` section.
4. Run `pytest` and, if you changed the plugin documentation, the sanity tests.
5. Open the pull request and fill in its template.

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
(`feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:`).

## Releasing (maintainers)

Releases are published to Ansible Galaxy by the `Release` workflow when a `v*` tag is pushed.

1. Update `version` in `galaxy.yml`. Move the `Unreleased` entries of `CHANGELOG.md` under a new
   `## [x.y.z] - YYYY-MM-DD` section and update the links at the bottom.
2. Commit with `chore: release x.y.z` and merge it into `main`.
3. Tag and push:

   ```bash
   git tag -a vx.y.z -m "x.y.z"
   git push origin vx.y.z
   ```

4. The workflow then:
   - checks that the tag matches `galaxy.yml`;
   - builds the collection and publishes it to Galaxy;
   - creates the GitHub release with the artifact.

The workflow needs the repository secret `GALAXY_API_KEY`, an API token of the `boukerramahmed`
namespace. To get it, open <https://galaxy.ansible.com>, then *Collections* and *API token*.
