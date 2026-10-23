# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

import json
from dataclasses import dataclass
from genlayer import *


VERIFIED = "verified"
NOT_FOUND = "not_found"
AUTHOR_MISMATCH = "author_mismatch"
UNVERIFIABLE = "unverifiable"

X_HOSTS = ("x.com", "twitter.com", "mobile.x.com", "mobile.twitter.com")


@allow_storage
@dataclass
class HandleStat:
    verified: u256  # authenticated, verified vouches only (positive-only reputation)


@allow_storage
@dataclass
class Check:
    claim_url: str
    handle: str  # normalized expected handle (no @, lowercase)
    url_host: str  # normalized host of the claim URL
    url_handle: str  # handle embedded in the URL path, "" if not parseable
    page_author: str  # author declared by the page's own HEAD metadata, "" if absent
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


def _host(url: str) -> str:
    u = _norm_url(url)
    return u.split("/", 1)[0] if "/" in u else u


def _norm_handle(h: str) -> str:
    """Normalize a handle: strip @, protocol, profile-URL forms, lowercase."""
    h = (h or "").strip().lstrip("@").lower()
    if "/" in h:
        h = h.rstrip("/").rsplit("/", 1)[-1]
    return h


def _url_handle(url: str) -> str:
    """Handle embedded in a status/profile URL path on the X/Twitter platform.

    https://x.com/<handle>/status/123 -> <handle>
    Returns "" when the URL does not live on x.com/twitter.com or carries no
    handle path.
    """
    u = _norm_url(url)
    host = u.split("/", 1)[0] if "/" in u else u
    if host not in X_HOSTS:
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


def _head_region(html: str) -> str:
    """Restrict authorship extraction to the <head> region.

    Authorship must come from structural metadata the platform/page owner
    emits, not from body text any arbitrary page can freely write.
    """
    h = html or ""
    low = h.lower()
    start = low.find("<head")
    if start < 0:
        return ""
    end = low.find("</head>", start)
    if end >= 0:
        return h[start:end]
    return h[start:start + 20000]


def _stat_delta(verdict: str) -> u256:
    """Positive-only reputation.

    A failed check (not_found / author_mismatch / unverifiable) submitted by
    an arbitrary caller must never subtract from a handle's standing, so only
    a verified verdict contributes to the aggregate. Third parties cannot
    make another handle look "unclean" through failed submissions.
    """
    return 1 if verdict == VERIFIED else 0


def _decide(
    handle: str,
    url_host: str,
    url_handle: str,
    page_author: str,
    found: bool,
    quote: str,
    quote_in_page: bool,
) -> tuple:
    """Deterministic verdict logic (pure, unit-tested).

    A verified result requires AUTHENTICATED authorship — the two structural
    signals together, on the platform itself:
      1. platform gate: the page must live on x.com/twitter.com. Self-declared
         metadata from an arbitrary domain can never verify anything (a
         spoofed site can simply write twitter:creator=anything).
      2. URL-path handle must equal the claimed handle, AND
      3. the author the page's own HEAD metadata attributes the post to must
         also equal the claimed handle.
    Neither signal alone is sufficient. A contradicting signal is stored as
    author_mismatch evidence; a missing signal is unverifiable. Authorship is
    authenticated BEFORE content, so a page that belongs to someone else can
    never be verified for the claimed handle, and a quote that is not
    verbatim in the page can never produce "verified".
    """
    if url_host not in X_HOSTS:
        return UNVERIFIABLE, ""
    if url_handle and url_handle != handle:
        return AUTHOR_MISMATCH, ""
    if page_author and page_author != handle:
        return AUTHOR_MISMATCH, ""
    if url_handle != handle or page_author != handle:
        return UNVERIFIABLE, ""
    if found and quote_in_page and quote:
        return VERIFIED, quote[:1000]
    return NOT_FOUND, ""


class VouchGuard(gl.Contract):
    """On-chain vouch verification for GenLayer.

    Anyone can submit a claim URL (a public page that supposedly contains a
    vouch, e.g. an X status) plus the handle that is expected to have made
    it. The contract:

    1. Keys results by (normalized URL, handle) - the same page can be checked
       against different handles independently, and a failed/ambiguous check
       can be retried. Only a "verified" verdict is final and immutable.
    2. Keeps reputation POSITIVE-ONLY: the per-handle aggregate counts solely
       authenticated verified vouches. Failed submissions never decrement or
       taint a handle, so an arbitrary caller cannot make another handle look
       unclean by submitting checks destined to fail.
    3. Requires AUTHENTICATED authorship for any verified result, from both
       structural signals on the platform itself (see _decide): the URL path
       handle AND the page's own HEAD-metadata author must both equal the
       claimed handle, and the page must live on x.com/twitter.com - either
       signal alone, or metadata from an arbitrary domain, never suffices.
    4. Verifies the quote against the page: the LLM-extracted supporting
       quote must appear verbatim in the fetched page text (deterministic
       containment check). A hallucinated quote cannot produce "verified".

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
            # Structural authorship evidence lives in the HTML <head> (title,
            # meta tags, profile links); the readable post text in the body.
            html = gl.nondet.web.render(claim_url, mode="html")
            text = gl.nondet.web.render(claim_url, mode="text")

            author_task = f"""
You are extracting AUTHORSHIP metadata from a webpage's HEAD region. Do not judge content.

Look ONLY at structural authorship signals in this HTML HEAD: the <title> tag
(pattern "Display Name on X: ..."), meta tags (twitter:creator, author,
og:title), profile/canonical links (x.com/<handle>, twitter.com/<handle>),
and JSON-LD author fields.

Which handle AUTHORED this page? Reply with JSON only:
{{"author_handle": "<handle without @, or empty string if the page carries no author metadata>"}}
If the page is an error/login/consent wall or shows no author metadata, use "".
"""
            author_raw = gl.nondet.exec_prompt(
                author_task + "\n\nHEAD region (first 20000 chars):\n" + _head_region(html)[:20000]
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

        def validator_fn(leader_res) -> bool:
            # Independent verification: re-run the same extraction here and
            # compare only the CONSENSUS-RELEVANT fields (authorship + found),
            # never raw LLM prose. Classifying the winner with gl.vm.Return.
            if not isinstance(leader_res, gl.vm.Return):
                return False
            try:
                raw = leader_res.calldata
                theirs = json.loads(raw if isinstance(raw, str) else str(raw))
                mine = json.loads(run())
            except Exception:
                return False
            return _norm_handle(str(theirs.get("author_raw", ""))) == _norm_handle(
                str(mine.get("author_raw", ""))
            ) and bool(theirs.get("found")) == bool(mine.get("found"))

        # Nondeterministic block: web fetch + two LLM calls, validated by an
        # independent re-run inside consensus (never strict_eq on LLM output).
        return json.loads(gl.vm.run_nondet_unsafe(run, validator_fn))

    @gl.public.write
    def submit_check(self, claim_url: str, expected_handle: str) -> str:
        key = _norm_url(claim_url) + "|" + _norm_handle(expected_handle)
        existing = self.checks.get(key)
        if existing is not None:
            if existing.verdict == VERIFIED:
                # A verified verdict is final; re-binding a verified page to
                # another check is pointless, other handles stay independent.
                raise gl.vm.UserError("Already verified for this handle")
            # notFound/author_mismatch/unverifiable are RETRYABLE: a first
            # caller can never permanently bind a page to a wrong handle.
            c = existing
            c.attempts += 1
        else:
            c = Check(
                claim_url=claim_url.strip(),
                handle=_norm_handle(expected_handle),
                url_host=_host(claim_url),
                url_handle="",
                page_author="",
                verdict="pending",
                quote="",
                attempts=1,
            )
            self.checks[key] = c

        url_handle = _url_handle(claim_url)
        res = self._analyze(claim_url, c.handle)
        c.url_host = _host(claim_url)
        c.url_handle = url_handle
        c.page_author = _norm_handle(str(res.get("author_raw", "")))
        found = bool(res.get("found"))
        quote = str(res.get("quote", ""))
        quote_in_page = bool(res.get("quote_in_page"))

        c.verdict, c.quote = _decide(
            c.handle, c.url_host, url_handle, c.page_author, found, quote, quote_in_page
        )

        self.total += 1
        # Positive-only reputation: failures never touch the handle aggregate,
        # so an arbitrary caller cannot make another handle look unclean.
        delta = _stat_delta(c.verdict)
        if delta:
            s = self.stats.get_or_insert_default(c.handle)
            s.verified += delta
        return c.verdict

    @gl.public.view
    def get_check(self, claim_url: str, expected_handle: str) -> dict:
        key = _norm_url(claim_url) + "|" + _norm_handle(expected_handle)
        if key not in self.checks:
            raise gl.vm.UserError("Unknown claim")
        c = self.checks[key]
        return {
            "claim_url": c.claim_url,
            "handle": c.handle,
            "url_host": c.url_host,
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
        h = _norm_handle(handle)
        s = self.stats.get(h, HandleStat(verified=0))
        return {
            "handle": h,
            "verified": s.verified,
            # "clean" is derived ONLY from positive evidence: third-party
            # failed submissions can never flip this to unclean.
            "clean": s.verified > 0,
        }
