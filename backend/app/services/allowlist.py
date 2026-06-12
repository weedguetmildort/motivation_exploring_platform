# backend/app/services/allowlist.py
import re
from typing import Optional, List
from datetime import datetime, timezone
from urllib.parse import urlparse
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError
from bson import ObjectId

from ..schemas.allowlist import AllowlistPublic


def get_allowlist_collection(db) -> Collection:
    return db["allowlist"]


def ensure_indexes(col: Collection) -> None:
    col.create_index("domain", unique=True)


# Common multi-part public suffixes where the registrable domain needs an
# extra label (e.g. "bbc.co.uk", not just "co.uk"). Not exhaustive (a full
# Public Suffix List would require an extra dependency), but covers the
# ccTLD patterns most likely to appear in educational/news sources.
_TWO_PART_SUFFIXES = frozenset({
    "co.uk", "ac.uk", "org.uk", "gov.uk", "sch.uk", "nhs.uk", "ltd.uk", "plc.uk",
    "co.jp", "ac.jp", "or.jp", "ne.jp", "go.jp",
    "co.in", "ac.in", "gov.in", "edu.in", "res.in",
    "edu.au", "gov.au", "org.au", "com.au", "net.au", "asn.au", "id.au",
    "edu.cn", "gov.cn", "com.cn", "org.cn", "net.cn",
    "ac.nz", "co.nz", "govt.nz", "org.nz", "net.nz",
    "co.za", "ac.za", "gov.za", "org.za", "net.za",
    "edu.sg", "gov.sg", "com.sg", "net.sg", "org.sg",
    "com.br", "gov.br", "org.br", "net.br",
})


def _extract_registrable_domain(url: str) -> Optional[str]:
    """Extract the registrable domain from a URL or bare domain.

    Strips scheme, path, www. prefix, and port. Lowercases the result.
    Normally returns the last 2 dot-separated parts, but for known
    multi-part public suffixes (e.g. "co.uk", "ac.jp") returns the last 3
    parts so e.g. "bbc.co.uk" isn't collapsed to "co.uk".
    Returns None if parsing fails or result has no dot.
    """
    try:
        # If no scheme, prepend one so urlparse works correctly
        if "://" not in url:
            url = "https://" + url
        host = urlparse(url).hostname or ""
        host = host.lower()
        # Strip leading www.
        if host.startswith("www."):
            host = host[4:]
        # Take the last two dot-separated parts as the registrable domain,
        # or the last three if the last two form a known multi-part suffix.
        parts = host.split(".")
        if len(parts) >= 2:
            last_two = ".".join(parts[-2:])
            if len(parts) >= 3 and last_two in _TWO_PART_SUFFIXES:
                return ".".join(parts[-3:])
            return last_two
        return host if host else None
    except Exception:
        return None


_DOMAIN_RE = re.compile(
    r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?)+$"
)


def _normalize_domain(raw: str) -> str:
    """Strip scheme, path, www prefix; lowercase. Raises ValueError on invalid format."""
    domain = _extract_registrable_domain(raw.strip())
    if not domain:
        raise ValueError(f"Cannot parse domain from: {raw!r}")
    if not _DOMAIN_RE.match(domain):
        raise ValueError(f"Invalid domain format: {domain!r}")
    return domain


def domain_is_allowed(url: str, allowlist_set: set) -> bool:
    """Return True if url's registrable domain (or any parent) is in allowlist_set."""
    registrable = _extract_registrable_domain(url)
    if not registrable:
        return False
    # Check registrable domain and subdomains iteratively
    # e.g. cs.stanford.edu -> check "stanford.edu" (already the registrable part)
    # For a URL like "deep.sub.example.com", registrable is "example.com" which is checked.
    return registrable in allowlist_set


def load_allowlist_cache(col: Collection) -> set:
    return {doc["domain"] for doc in col.find({}, {"domain": 1})}


def _to_public(doc: dict) -> AllowlistPublic:
    return AllowlistPublic(
        id=str(doc["_id"]),
        domain=doc["domain"],
        added_by=doc.get("added_by", ""),
        added_at=doc["added_at"],
    )


def list_domains(col: Collection) -> List[AllowlistPublic]:
    docs = col.find().sort("added_at", -1)
    return [_to_public(doc) for doc in docs]


def add_domain(col: Collection, domain_raw: str, added_by: str) -> AllowlistPublic:
    """Normalize and insert a domain. Raises ValueError on bad format, DuplicateKeyError on dup."""
    domain = _normalize_domain(domain_raw)
    now = datetime.now(timezone.utc)
    doc = {"domain": domain, "added_by": added_by, "added_at": now}
    try:
        res = col.insert_one(doc)
    except DuplicateKeyError:
        raise DuplicateKeyError(f"Domain already in allowlist: {domain}")
    doc["_id"] = res.inserted_id
    return _to_public(doc)


def remove_domain(col: Collection, domain_id: str) -> Optional[AllowlistPublic]:
    if not ObjectId.is_valid(domain_id):
        return None
    doc = col.find_one({"_id": ObjectId(domain_id)})
    if not doc:
        return None
    col.delete_one({"_id": ObjectId(domain_id)})
    return _to_public(doc)
