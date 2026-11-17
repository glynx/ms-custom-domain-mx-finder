#!/usr/bin/env python3
"""Find the Exchange Online (Microsoft 365) MX host name for a custom domain.

Exchange Online builds the MX target from the domain itself:

    example.com          -> example-com.mail.protection.outlook.com
    example-domain.com   -> exampledomain-com01e.mail.protection.outlook.com

For domains with hyphens the suffix is not random: it encodes the positions
of the hyphens (chunks of four characters, one letter per chunk).

The script first reads the domain's existing MX records. If one of them is a
Microsoft 365 target, that value is used directly. Otherwise the encoded
candidate is generated and checked via DNS A lookups, with a small fallback
set if needed.

Requirements: rich and dnspython (see pyproject.toml).

This is a vibe-coded helper, not an official Microsoft tool. No warranty.
Always verify the MX value in the Microsoft 365 admin center.
"""

from __future__ import annotations

import argparse
import logging
import string
import sys

import dns.exception
import dns.resolver
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

DEFAULT_MX_DOMAIN = "mail.protection.outlook.com"
DNS_TIMEOUT = 5.0
LOG = logging.getLogger("mxfinder")
CONSOLE = Console()

# MX targets that indicate Exchange Online / Microsoft 365.
MICROSOFT_MX_SUFFIXES = (
    ".mail.protection.outlook.com",
    ".mail.eo.outlook.com",
    ".mail.protection.outlook.de",
    ".mx.microsoft",
)


def mx_token(domain: str) -> str:
    """Return the host label Exchange Online uses for ``domain``.

    The result does not include ``.mail.protection.outlook.com``.
    """
    domain = domain.strip().rstrip(".").lower()

    # Build the hyphen token.  The domain is processed in chunks of four
    # characters.  Each hyphen sets one bit in a bitmask: the first hyphen
    # in a chunk adds 1, the second 2, the third 4, and the fourth 8.  The
    # bitmask is then written as a letter, starting at 'a' (no hyphen).
    encoded = []
    skipped_chunks = 0
    for start in range(0, len(domain), 4):
        chunk = domain[start : start + 4]
        value = ord("a")
        for offset, char in enumerate(chunk):
            if char == "-":
                value += 1 << offset

        if value == ord("a"):
            # No hyphen in this chunk.  Runs of empty chunks are compressed
            # to a single decimal digit before the next letter.
            skipped_chunks += 1
            continue

        if skipped_chunks:
            encoded.append(str(skipped_chunks))
            skipped_chunks = 0
        encoded.append(chr(value))

    # Remove the hyphens, turn dots into hyphens, and append the token.
    token = domain.replace("-", "").replace(".", "-")
    if encoded:
        token += "0" + "".join(encoded)
    return token


def plain_token(domain: str) -> str:
    """Return the host label without the hyphen token."""
    return domain.strip().rstrip(".").lower().replace("-", "").replace(".", "-")


def mx_candidates(domain: str, bruteforce: bool = True):
    """Yield MX host labels for ``domain``, most likely candidate first."""
    yield mx_token(domain)

    if "-" not in domain or not bruteforce:
        return

    base = plain_token(domain)

    # Real-world examples: ...-com0i, ...-com01i, ...-com02b, ...-com01cc.
    # The exact token above already handles all of these; the patterns below
    # are only a safety net if the format changes.
    for letter in string.ascii_lowercase:
        yield base + "0" + letter
    for digit in string.digits:
        for letter in string.ascii_lowercase:
            yield base + "0" + digit + letter


def candidate_list(domain: str, bruteforce: bool = True) -> list[str]:
    """Return all unique candidates for ``domain``."""
    seen: set[str] = set()
    result = []
    for token in mx_candidates(domain, bruteforce=bruteforce):
        if token not in seen:
            seen.add(token)
            result.append(token)
    return result


def is_microsoft_mx(host: str) -> bool:
    """Return True if ``host`` is an Exchange Online MX target."""
    host = host.strip().rstrip(".").lower()
    return any(host.endswith(suffix) for suffix in MICROSOFT_MX_SUFFIXES)


def resolve_mx(domain: str) -> list[tuple[int, str]]:
    """Return ``(priority, host)`` MX records for ``domain``, lowest priority first."""
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=DNS_TIMEOUT)
    except dns.exception.DNSException:
        return []

    records = []
    for answer in answers:
        host = str(answer.exchange).rstrip(".").lower()
        if host:  # ignore a null MX ("0 .")
            records.append((int(answer.preference), host))
    return sorted(records)


def microsoft_mx_records(records: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Filter MX records down to Microsoft 365 targets."""
    return [(priority, host) for priority, host in records if is_microsoft_mx(host)]


def resolve_a(host: str) -> list[str]:
    """Return the IPv4 addresses for ``host``, or an empty list."""
    try:
        answers = dns.resolver.resolve(host, "A", lifetime=DNS_TIMEOUT)
    except dns.exception.DNSException:
        return []
    return sorted({str(answer) for answer in answers})


def find_mx(
    domain: str, candidates: list[str], progress: Progress
) -> tuple[str | None, list[str], int]:
    """Check candidates and return ``(host, addresses, tried)`` for the first hit."""
    task = progress.add_task(f"[cyan]{domain}[/]", total=len(candidates))

    try:
        for index, token in enumerate(candidates, start=1):
            host = f"{token}.{DEFAULT_MX_DOMAIN}"
            progress.update(task, description=f"[cyan]{domain}[/] [dim]{token}[/]")
            addresses = resolve_a(host)
            LOG.debug("A lookup %3d/%d %s -> %s", index, len(candidates), host, addresses or "no record")
            progress.advance(task)

            if addresses:
                return host, addresses, index
    finally:
        progress.remove_task(task)

    return None, [], len(candidates)


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=CONSOLE, show_path=False, rich_tracebacks=True)],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find the Exchange Online MX host for custom domains: use an "
            "existing Microsoft MX record or generate candidates and check "
            "them via DNS A lookups."
        ),
        epilog=(
            "Vibecoded helper, no warranty. Always verify the MX value in the "
            "Microsoft 365 admin center. Examples: microsoft.com, atos.net, "
            "british-airways.com, van-lanschot.com, berliner-zeitung.de, "
            "john-lewis.co.uk"
        ),
    )
    parser.add_argument("domains", nargs="+", metavar="DOMAIN", help="mail domain to check")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="log MX lookups, candidates and A lookup results",
    )
    parser.add_argument(
        "--no-mx",
        action="store_true",
        help="skip the MX lookup and always generate candidates",
    )
    parser.add_argument(
        "--no-bruteforce",
        action="store_true",
        help="only try the calculated candidate, skip fallback suffixes",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)

    progress_columns = (
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    )

    failures = 0
    with Progress(*progress_columns, console=CONSOLE, transient=True) as progress:
        for domain in args.domains:
            mx_records: list[tuple[int, str]] = []
            if args.no_mx:
                LOG.info("Skipping MX lookup for %s (--no-mx)", domain)
            else:
                mx_records = resolve_mx(domain)
                LOG.debug(
                    "MX records for %s: %s",
                    domain,
                    ", ".join(f"{priority} {host}" for priority, host in mx_records) or "none",
                )

                ms_records = microsoft_mx_records(mx_records)
                if ms_records:
                    priority, host = ms_records[0]
                    LOG.info(
                        "Using Microsoft MX for %s: %s (priority %d)",
                        domain,
                        host,
                        priority,
                    )
                    addresses = resolve_a(host)
                    CONSOLE.print(f"[green]MX {priority}[/] {host}.")
                    if addresses:
                        CONSOLE.print(f"[green]A   [/] {', '.join(addresses)}")
                    else:
                        LOG.warning(
                            "MX target %s has no A record (NXDOMAIN or no data)",
                            host,
                        )
                        CONSOLE.print(
                            "[yellow]A   [/] no A record - target may not be provisioned yet"
                        )
                    continue

                if mx_records:
                    LOG.info(
                        "%s has %d non-Microsoft MX record(s); trying generated candidates",
                        domain,
                        len(mx_records),
                    )
                else:
                    LOG.info("No MX records for %s; trying generated candidates", domain)

            candidates = candidate_list(domain, bruteforce=not args.no_bruteforce)
            LOG.info("Generated %d candidate(s) for %s", len(candidates), domain)

            host, addresses, tried = find_mx(domain, candidates, progress)
            if host is None:
                failures += 1
                LOG.warning(
                    "No A record found for %s after %d candidate(s)",
                    domain,
                    tried,
                )
                CONSOLE.print(
                    "  hint: target may not be provisioned/verified yet "
                    "(new or moved domain), or the tenant may use *.mx.microsoft"
                )
                continue

            LOG.info("Found generated MX host for %s after %d candidate(s)", domain, tried)
            CONSOLE.print(f"[green]MX 0[/] {host}.")
            CONSOLE.print(f"[green]A   [/] {', '.join(addresses)}")

    LOG.info("Done: %d domain(s) checked, %d without result", len(args.domains), failures)
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
