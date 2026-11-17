# ms-custom-domain-mx-finder

> **Vibecoded disclaimer:** This is a vibe-coded helper, tested against a
> handful of public domains. It is not an official Microsoft tool and comes
> with no warranty. It may not work for every tenant, endpoint or DNS setup.
> Always verify the MX value in the Microsoft 365 admin center before changing
> production DNS.

Generate the Exchange Online (Microsoft 365) MX host for a custom domain and
check whether it exists in DNS. No access to the tenant is needed.

The tool first reads the domain's **existing MX records**. If one of them is a
Microsoft 365 target, that value is used directly — no brute force, no guessing.
Only when no Microsoft MX exists does it calculate candidates from the domain
name and test them via DNS A lookups.

Exchange Online does not use a fixed MX host. It derives the target from the
domain itself:

| Domain | MX target |
| --- | --- |
| `example.com` | `example-com.mail.protection.outlook.com` |
| `example-domain.com` | `exampledomain-com01e.mail.protection.outlook.com` |

The part after `-com` is not random. It encodes **where the hyphens are**,
which is why the tool can calculate it and only use DNS to verify.

## Install with uv

Run from the checkout (uv creates an isolated environment automatically):

```console
$ uv run mxfinder british-airways.com
```

Install it as a global command:

```console
$ uv tool install .
$ mxfinder british-airways.com
```

For development, install the project in editable mode:

```console
$ uv tool install --editable .
```

`rich` and `dnspython` are declared in `pyproject.toml` and are installed
automatically.

## Usage

```console
$ mxfinder [OPTIONS] DOMAIN [DOMAIN ...]
```

Options:

| Option | Description |
| --- | --- |
| `-v`, `--verbose` | Log every MX lookup, candidate and A lookup (DEBUG). |
| `--no-mx` | Skip the MX lookup and always generate candidates. |
| `--no-bruteforce` | Only try the calculated candidate, skip fallback suffixes. |

By default the tool uses this order:

1. Read the domain's MX records. If a Microsoft 365 target is present, use the
   lowest-priority one and report it.
2. If the selected MX target has no A record (for example because the domain is
   new or was just moved), report the MX value anyway and print a warning.
3. If no Microsoft MX exists, generate the calculated candidate and test it via
   an A lookup.
4. If that fails and brute force is enabled, try the fallback suffixes.

Progress bars and log lines show what is happening; the final `MX` line is
ready to be used as a DNS record.

Example:

```console
$ uv run mxfinder british-airways.com
[18:59:43] INFO     Using Microsoft MX for british-airways.com:
                    britishairways-com01i.mail.protection.outlook.com (priority 0)
MX 0 britishairways-com01i.mail.protection.outlook.com.
A    52.101.103.162, 52.101.181.156, 52.101.68.12, 52.101.73.120
```

If the MX record exists but the target does not resolve yet:

```console
$ uv run mxfinder madeleine-mode.com
[18:59:43] INFO     Using Microsoft MX for madeleine-mode.com:
                    madeleinemode-com02c.mail.protection.outlook.com (priority 30)
MX 30 madeleinemode-com02c.mail.protection.outlook.com.
           WARNING  MX target madeleinemode-com02c.mail.protection.outlook.com
                    has no A record (NXDOMAIN or no data)
A    no A record - target may not be provisioned yet
```

## How the hyphen token works

The domain is split into chunks of four characters. Each chunk gets one
letter:

1. Start at `a` (decimal `97`).
2. For every hyphen in the chunk, add its bit value: first position `1`,
   second `2`, third `4`, fourth `8`.
3. Convert the result back to a letter, so a chunk without a hyphen is `a`,
   one hyphen at the first position is `b`, and so on.
4. Chunks without a hyphen are skipped, but the number of skipped chunks is
   written as a decimal digit before the next letter.

Finally the hyphens are removed, dots become hyphens, and `0` + token is
appended.

Worked examples:

| Domain | Chunks | Token | MX host |
| --- | --- | --- | --- |
| `british-airways.com` | `brit`, `ish-`, `airw`, `ays.`, `com` | `1i` (one skipped chunk, hyphen at offset 3) | `britishairways-com01i` |
| `van-lanschot.com` | `van-`, `lans`, `chot`, `.com` | `i` (hyphen at offset 3, no skipped chunk) | `vanlanschot-com0i` |
| `berliner-zeitung.de` | `berl`, `iner`, `-zei`, `tung`, `.de` | `2b` (two skipped chunks, hyphen at offset 0) | `berlinerzeitung-de02b` |

## Verified public examples

These domains were checked against live DNS while writing the tool. IPs and
some endpoints change over time, but the host names follow the rules above.

| Domain | Computed MX host | Pattern demonstrated |
| --- | --- | --- |
| `microsoft.com` | `microsoft-com.mail.protection.outlook.com` | no hyphen |
| `atos.net` | `atos-net.mail.protection.outlook.com` | no hyphen, non-`.com` TLD |
| `british-airways.com` | `britishairways-com01i.mail.protection.outlook.com` | hyphen, one skipped chunk |
| `van-lanschot.com` | `vanlanschot-com0i.mail.protection.outlook.com` | hyphen in the first chunk, no skip digit |
| `berliner-zeitung.de` | `berlinerzeitung-de02b.mail.protection.outlook.com` | two skipped chunks |
| `john-lewis.co.uk` | `johnlewis-co-uk01b.mail.protection.outlook.com` | multi-label TLD |
| `schwarz-group.com` | `schwarzgroup-com01i.mail.protection.outlook.com` | hyphen |
| `siemens-healthineers.com` | `siemenshealthineers-com01i.mail.protection.outlook.com` | long domain |

Run them all:

```console
$ uv run mxfinder microsoft.com atos.net british-airways.com \
    van-lanschot.com berliner-zeitung.de john-lewis.co.uk \
    schwarz-group.com siemens-healthineers.com
```

## Notes and limitations

- The tool reads the domain's existing MX records first. Microsoft targets
  under `mail.protection.outlook.com`, `mail.eo.outlook.com` and
  `*.mx.microsoft` are recognized.
- `mail.eo.outlook.com` is a **wildcard** zone: almost every name below it
  resolves. An A lookup there is therefore not a reliable check.
- A missing A record does not prove that a domain is not on Microsoft 365.
  The authoritative value is always shown in the Microsoft 365 admin center
  under **Settings → Domains**.
- A domain can already have an MX record pointing to the calculated host
  while Microsoft has not created the A record yet. This is common for newly
  added or moved domains and can take hours (sometimes a Microsoft support
  case is needed). Keep the old MX as a fallback until the target resolves.
  The tool reports such an MX value and prints a warning instead of hiding it.
- The fallback brute force tries `0<letter>` and `0<digit><letter>` patterns.
  The calculated candidate is always tried first and normally succeeds.
- Only IPv4 A records are queried.
- Exit code is `1` only when no MX target could be found at all. An MX value
  whose A record is missing is still reported (with a warning) and exits `0`.

### Troubleshooting a non-resolving target

If the calculated host is `NXDOMAIN`, check:

```console
$ dig +short MX example.com
$ dig +short A example-com.mail.protection.outlook.com
$ dig +short CNAME selector1._domainkey.example.com
$ dig +short MX tenant.onmicrosoft.com
```

The DKIM CNAME contains the same hyphen token and the tenant name, e.g.
`selector1-example-com01i._domainkey.contoso.onmicrosoft.com`. If that exists
but the MX target does not, the domain is known to the tenant but the
custom-domain MX host has not been provisioned yet. Check the domain status
and the exact MX value in the Microsoft 365 admin center.

## Development

Run the unit tests for the token calculation:

```console
$ uv run python -m unittest discover -s tests -v
```
