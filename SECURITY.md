# Security Policy

## Supported versions

Security fixes are released for the latest minor version of the collection.

| Version | Supported |
|---|---|
| 0.1.x | ✅ |

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through GitHub:
[Report a vulnerability](https://github.com/boukerramAhmed/ansible-collection-cloudtemple/security/advisories/new)
(*Security* tab → *Report a vulnerability*).

Please include:

- the affected version of the collection and of ansible-core;
- a description of the issue and its impact;
- the steps or the configuration needed to reproduce it, **without real credentials**.

You can expect:
- an acknowledgement within 7 days;
- an assessment and a remediation plan within 30 days.

The fix is released with a GitHub security advisory that credits you, unless you prefer to stay
anonymous.

## Scope

The collection runs on the Ansible controller and handles Cloud Temple credentials. Reports
are especially welcome about:

- leaks of the Personal Access Token or of the JWT: logs, error messages, inventory cache,
  `ansible-inventory` output;
- TLS certificate validation being bypassed while `validate_certs` is `true`;
- injection through API data, for example a crafted VM or network name that ends up in group
  names or host variables.

Vulnerabilities of the Cloud Temple platform itself are out of scope: report them to
Cloud Temple.

## Hardening recommendations

- Use a **read-only** Personal Access Token, limited to one tenant, with the shortest expiry
  you can manage.
- Pass `CLOUDTEMPLE_CLIENT_ID` / `CLOUDTEMPLE_SECRET_ID` through environment variables or your CI
  secret store, never in a committed inventory file.
- Keep `validate_certs: true`.
