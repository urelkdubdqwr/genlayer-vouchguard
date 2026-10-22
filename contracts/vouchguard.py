# { "Depends": "py-genlayer:test" }

import json
from dataclasses import dataclass
from genlayer import *


VERIFIED = "verified"
NOT_FOUND = "not_found"
AUTHOR_MISMATCH = "author_mismatch"
UNVERIFIABLE = "unverifiable"


@allow_storage
@dataclass
class HandleStat:
    attempts: u256  # total checks submitted for this handle
    verified: u256  # how many attempts resolved to "verified"


@allow_storage
@dataclass
class Check:
    claim_url: str
    handle: str  # normalized expected handle (no @, lowercase)
    url_handle: str  # handle embedded in the URL path, "" if not parseable
    page_author: str  # handle the PAGE ITSELF attributes authorship to (metadata)
    verdict: str  # verified | not_found | author_mismatch | unverifiable
    quote: str  # exact quote from the page (only when verified)
    attempts: u256


def _norm_url(url: str) -> str:
    """Deterministic URL normalization for storage keys."""
    u = (url or "").strip()
    for prefix in ("https://", "http://", "www."):
        if u.lower().startswith(prefix):
            u = u[len(prefix):]
    return u.rstrip("/").lower()


def _norm_handle(h: str) -> str:
    """Normalize a handle: strip @, protocol, profile-URL forms, lowercase."""
    h = (h or "").strip().lstrip("@").lower()
    if "/" in h:
        h = h.rstrip("/").rsplit("/", 1)[-1]
    return h


def _url_handle(url: str) -> str:
    """Handle embedded in a status/profile URL path.

    https://x.com/<handle>/status/123 -> <handle>
    Returns "" when the URL does not carry a handle path.
    """
    u = _norm_url(url)
    host = u.split("/", 1)[0] if "/" in u else u
    if host not in ("x.com", "twitter.com", "mobile.x.com", "mobile.twitter.com"):
        return ""
    path = u[len(host):].strip("/")
    if not path:
        return ""
    first = path.split("/")[0]
    if first in ("i", "home", "explore", "search", "hashtag", "intent"):
        return ""
    return first


def _norm_text(s: str) -> str:
    return " ".join((s or "").lower().split())


def _quote_in_page(quote: str, page_text: str) -> bool:
    """Deterministic containment check: the LLM-extracted quote must exist
    verbatim (whitespace/case-insensitive) in the fetched page text.
    Prevents hallucinated quotes from ever being bound on-chain."""
    q = _norm_text(quote)
    return bool(q) and q in _norm_text(page_text)


class VouchGuard(gl.Contract):
    """On-chain vouch verification for GenLayer.

    Anyone can submit a claim URL (a public page that supposedly contains a
    vouch/endorsement, e.g. an X status) plus the handle that is expected to
    have made it. The contract:

    1. Keys results by (normalized URL, handle) - the same page can be checked
       against different handles, and a failed/ambiguous check can be retried.
       Only a "verified" verdict is final and immutable, so a first caller can
       never permanently bind a page to the wrong handle.
    2. Authenticates authorship structurally: the handle embedded in the page
       URL (x.com/<handle>/status/...) is compared against the expected handle,
       AND the author the page's own metadata attributes the post to (title,
       twitter:creator, profile links, JSON-LD) is extracted independently of
       the claim. Mismatch -> verdict "author_mismatch" is stored as evidence,
       it never silently verifies.
    3. Verifies the quote against the page: the LLM-extracted supporting quote
       must appear verbatim in the fetched page text (deterministic containment
       check). A quote that is not in the page cannot produce "verified".

    The verdict, the exact supporting quote and the authorship evidence become
    immutable, publicly queryable on-chain history.
    """

    checks: TreeMap[str, Check]
    stats: TreeMap[str, HandleStat]
    total: u256

    def __init__(self):
        pass

    def _analyze(self, claim_url: str, handle_norm: str) -> dict:
        def run() -> str:
            # Structural authorship evidence lives in the HTML (title, meta,
            # profile links), the readable post text in the rendered text.
            html = gl.get_webpage(claim_url, mode="html")
            text = gl.get_webpage(claim_url, mode="text")

            author_task = f"""
You are extracting AUTHORSHIP metadata from a webpage. Do not judge content.

Look ONLY at structural authorship signals in this HTML: the <title> tag
(pattern "Display Name on X: ..."), meta tags (twitter:creator, author,
og:title), profile/canonical links (x.com/<handle>, twitter.com/<handle>),
and JSON-LD author fields.

Which handle AUTHORED this page? Reply with JSON only:
{{"author_handle": "<handle without @, or empty string if the page carries no author metadata>"}}
If the page is an error/login/consent wall or shows no author metadata, use "".
"""
            author_raw = gl.exec_prompt(
                author_task + "\n\nHTML (first 20000 chars):\n" + html[:20000]
            ).replace("```json", "").replace("```", "")
            author = json.loads(author_raw).get("author_handle", "")

            vouch_task = f"""
You are verifying a public endorsement ("vouch").
The page author is @{handle_norm}.

Decide whether this page text contains a post written by @{handle_norm} that
publicly vouches for, endorses or attests to someone's trustworthiness.
Do not treat a MENTION of @{handle_norm} (someone else quoting them) as
authorship - only their own post counts.

Page text:
{text[:30000]}

Respond in JSON:
{{
    "found": bool,
    "quote": str
}}
"found" is true only if the text actually contains such a post by
@{handle_norm}, and "quote" is the exact sentence copied from the page (or ""
if not found). It is mandatory that you respond only using the JSON format
above, nothing else. Don't include any other words or characters, your output
must be only JSON without any formatting prefix or suffix. This result should
be perfectly parsable by a JSON parser without errors.
"""
            vouch_raw = gl.exec_prompt(vouch_task).replace("```json", "").replace("```", "")
            vouch = json.loads(vouch_raw)

            return json.dumps(
                {
                    "author_raw": str(author),
                    "found": bool(vouch.get("found")),
                    "quote": str(vouch.get("quote", "")),
                    "quote_in_page": _quote_in_page(str(vouch.get("quote", "")), text),
                },
                sort_keys=True,
            )

        return json.loads(gl.eq_principle_strict_eq(run))

    @gl.public.write
    def submit_check(self, claim_url: str, expected_handle: str) -> str:
        key = _norm_url(claim_url) + "|" + _norm_handle(expected_handle)
        existing = self.checks.get(key)
        if existing is not None:
            if existing.verdict == VERIFIED:
                # A verified verdict is final; re-binding a verified page to
                # another check is pointless, other handles stay independent.
                raise Exception("Already verified for this handle")
            # notFound/author_mismatch/unverifiable are RETRYABLE: a first
            # caller can never permanently bind a page to a wrong handle.
            c = existing
            c.attempts += 1
        else:
            c = Check(
                claim_url=claim_url.strip(),
                handle=_norm_handle(expected_handle),
                url_handle="",
                page_author="",
                verdict="pending",
                quote="",
                attempts=1,
            )
            self.checks[key] = c

        url_handle = _url_handle(claim_url)
        author_page = _norm_handle(str(c.page_author))
        c.url_handle = url_handle

        res = self._analyze(claim_url, c.handle)
        c.page_author = _norm_handle(str(res.get("author_raw", "")))
        found = bool(res.get("found"))
        quote = str(res.get("quote", ""))
        quote_in_page = bool(res.get("quote_in_page"))

        if c.page_author and c.page_author != c.handle:
            # The page itself attributes authorship to someone else.
            c.verdict = AUTHOR_MISMATCH
            c.quote = ""
        elif url_handle and url_handle != c.handle:
            # The URL path carries a different handle than claimed.
            c.verdict = AUTHOR_MISMATCH
            c.quote = ""
        elif not c.page_author and not url_handle:
            # No structural authorship evidence at all: cannot verify.
            c.verdict = UNVERIFIABLE
            c.quote = ""
        elif found and quote_in_page and quote:
            # Authorship confirmed AND quote verbatim in the fetched page.
            c.verdict = VERIFIED
            c.quote = quote[:1000]
        else:
            c.verdict = NOT_FOUND
            c.quote = ""

        self.total += 1
        s = self.stats.get_or_insert_default(c.handle)
        s.attempts += 1
        if c.verdict == VERIFIED:
            s.verified += 1
        return c.verdict

    @gl.public.view
    def get_check(self, claim_url: str, expected_handle: str) -> dict:
        key = _norm_url(claim_url) + "|" + _norm_handle(expected_handle)
        if key not in self.checks:
            raise Exception("Unknown claim")
        c = self.checks[key]
        return {
            "claim_url": c.claim_url,
            "handle": c.handle,
            "url_handle": c.url_handle,
            "page_author": c.page_author,
            "verdict": c.verdict,
            "quote": c.quote,
            "attempts": c.attempts,
        }

    @gl.public.view
    def has_check(self, claim_url: str, expected_handle: str) -> bool:
        key = _norm_url(claim_url) + "|" + _norm_handle(expected_handle)
        return key in self.checks

    @gl.public.view
    def total_checks(self) -> int:
        return self.total

    @gl.public.view
    def get_handle_stats(self, handle: str) -> dict:
        s = self.stats.get(_norm_handle(handle), HandleStat(0, 0))
        return {
            "handle": _norm_handle(handle),
            "attempts": s.attempts,
            "verified": s.verified,
            "clean": s.attempts > 0 and s.verified == s.attempts,
        }
