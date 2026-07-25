# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately to
`info@sacrosaunt.com`. Do not open a public issue for an unpatched security
problem or include credentials, personal data, or exploit details in a public
discussion.

Include the affected version or commit, a concise reproduction, the expected
impact, and any suggested mitigation. We will attempt to acknowledge a report
within five business days and coordinate disclosure after a fix is available.

## Supported version

Security fixes target the current `main` branch. Self-hosters should update to
the newest release or commit and rebuild their container after a security fix.

## Deployment boundary

The self-hosted HTTP transport does not include authentication or TLS. Keep it
on loopback or a private network unless it is protected by an authenticated
reverse proxy and firewall. Do not enable proxy-specific client-IP trust outside
the proxy environment it was designed for.
