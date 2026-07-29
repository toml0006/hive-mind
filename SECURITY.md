# Security policy

Hive Mind stores potentially sensitive organizational memory. Treat scope
isolation failures, unintended data disclosure, authentication bypasses, and
destructive graph mutations as security issues.

## Supported versions

The project is currently alpha. Security fixes are made on the default branch
and included in the next release. Older snapshots are not separately supported.

## Reporting

Do not open a public issue for a suspected vulnerability or privacy leak.

Use GitHub's
[Report a vulnerability](https://github.com/toml0006/hive-mind/security/advisories/new)
form in the repository's Security tab.
If private vulnerability reporting is unavailable, contact a maintainer
privately and ask for a secure reporting channel without including exploit
details or sensitive data in the first message.

Include:

- affected commit or version;
- impact and affected trust boundary;
- minimal reproduction using synthetic data;
- whether credentials or project-scoped memory may have been exposed;
- any suggested mitigation.

Never attach a real Neo4j database, transcript, email, meeting note, repository
map, token, or credential.

Maintainers will acknowledge a complete report as soon as practical, keep the
reporter informed, and coordinate disclosure after a fix is available.

## Deployment assumptions

The development stack binds Neo4j to localhost and uses a known development
password. It is not a production security configuration.

Operators are responsible for:

- unique credentials and a trusted network boundary;
- encrypted backups and tested recovery;
- filesystem protection for local candidate queues and logs;
- reviewing repository-to-project mappings;
- controlling which agents may invoke write tools;
- keeping the web app private unless authentication is added.

The web API is same-origin protected but does not currently provide multi-user
authentication or authorization.
