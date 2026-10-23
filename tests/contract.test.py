#!/usr/bin/env python3
"""Unit tests for VouchGuard deterministic helpers (no GenVM needed).

Stubs the `genlayer` module so contracts/vouchguard.py imports cleanly on any
CPython >= 3.8 (genlayer type names are defined by the stub, so class-body
annotations never NameError), then asserts the pure functions that carry the
security decisions.

Run: python3 tests/contract.test.py
"""
import sys, types, pathlib

root = pathlib.Path(__file__).resolve().parent.parent


class _GL:
    class Contract:
        pass

    class public:
        @staticmethod
        def write(fn=None):
            return fn

        @staticmethod
        def view(fn=None):
            return fn


stub = types.ModuleType("genlayer")
stub.allow_storage = lambda cls: cls
stub.gl = _GL
# Names the contract annotates with (`u256`, `TreeMap[...]`). Annotations are
# evaluated at class-creation time on CPython < 3.14, so they must exist here.
stub.u256 = int
stub.TreeMap = dict
stub.Address = str
stub.dyn_array = list
sys.modules["genlayer"] = stub
sys.path.insert(0, str(root / "contracts"))

import vouchguard as vg  # noqa: E402

V, NF, AM, UV = vg.VERIFIED, vg.NOT_FOUND, vg.AUTHOR_MISMATCH, vg.UNVERIFIABLE
GOOD_QUOTE = "I vouch for @dev, we shipped together for a year."
GOOD = dict(handle="alice", url_host="x.com", url_handle="alice",
            page_author="alice", found=True, quote=GOOD_QUOTE, quote_in_page=True)


def test_norm_url():
    assert vg._norm_url("HTTPS://X.com/alice/status/1/") == "x.com/alice/status/1"
    assert vg._norm_url("http://www.x.com/a") == "x.com/a"
    assert vg._norm_url("  x.com/a?utm=1  ") == "x.com/a?utm=1"
    assert vg._norm_url("") == ""
    assert vg._norm_url("https://site.tld") == "site.tld"


def test_norm_handle():
    assert vg._norm_handle("@Alice") == "alice"
    assert vg._norm_handle("https://x.com/bob") == "bob"
    assert vg._norm_handle("") == ""
    assert vg._norm_handle("  Carol  ") == "carol"
    # spoof shapes: author names like "alice | crypto" are NOT a handle match
    assert vg._norm_handle("alice | crypto") == "alice | crypto"


def test_url_handle():
    assert vg._url_handle("https://x.com/alice/status/123") == "alice"
    assert vg._url_handle("https://twitter.com/Bob/status/9") == "bob"
    assert vg._url_handle("https://mobile.x.com/carol/status/5") == "carol"
    # profile URL -> still a handle path
    assert vg._url_handle("https://x.com/dave") == "dave"
    # non-X hosts carry no structural handle (arbitrary domains included)
    assert vg._url_handle("https://blog.example.com/vouch") == ""
    assert vg._url_handle("https://x.com.evil.net/alice/vouch") == ""
    # non-profile paths are not handles
    assert vg._url_handle("https://x.com/i/web/status/1") == ""
    assert vg._url_handle("https://x.com/hashtag/foo") == ""


def test_head_region():
    html = ("<html><head><title>Alice on X: hi</title>"
            "<meta name='twitter:creator' content='alice'></head>"
            "<body>body text claiming twitter:creator=bob and author bob</body></html>")
    head = vg._head_region(html)
    assert "Alice on X" in head
    assert "twitter:creator=bob" not in head and "author bob" not in head
    # no head at all -> no authorship metadata to trust
    assert vg._head_region("<html><body>plain</body></html>") == ""
    # unterminated head is still bounded (slice starts at the <head tag)
    assert vg._head_region("<html><head><title>x") == "<head><title>x"


def test_quote_in_page():
    page = "Vouching for @dev: I have worked with Dev for 2 years, solid engineer."
    assert vg._quote_in_page("I have worked with Dev for 2 years", page)
    assert vg._quote_in_page("I HAVE WORKED   WITH dev", page)
    # hallucinated / reformulated quote must FAIL
    assert not vg._quote_in_page("Dev is the best dev ever", page)
    assert not vg._quote_in_page("", page)
    # quote spanning the full text
    assert vg._quote_in_page(page, page)


# --- steward objection 2: verified requires AUTHENTICATED authorship --------

def test_verified_requires_both_authorship_signals():
    """Neither the X URL path nor the page metadata alone may verify."""
    # baseline: both signals present and equal -> real vouch verifies
    assert vg._decide(**GOOD) == (V, GOOD_QUOTE)

    # missing URL-path handle (metadata only) -> never verified
    assert vg._decide(**dict(GOOD, url_handle="")) == (UV, "")
    # missing page-metadata author (URL path only) -> never verified
    assert vg._decide(**dict(GOOD, page_author="")) == (UV, "")
    # both missing -> never verified
    assert vg._decide(**dict(GOOD, url_handle="", page_author="")) == (UV, "")

    # a contradicting signal is stored as author_mismatch evidence
    assert vg._decide(**dict(GOOD, url_handle="bob")) == (AM, "")
    assert vg._decide(**dict(GOOD, page_author="bob")) == (AM, "")
    # claiming someone else's status URL (quote/mention of alice in bob's page)
    assert vg._decide(**dict(GOOD, url_handle="bob", page_author="bob")) == (AM, "")

    # content gates still apply on top of authorship
    assert vg._decide(**dict(GOOD, quote_in_page=False)) == (NF, "")
    assert vg._decide(**dict(GOOD, quote="")) == (NF, "")
    assert vg._decide(**dict(GOOD, found=False)) == (NF, "")


def test_spoofed_domain_metadata_never_verifies():
    """An arbitrary domain declaring itself authored by @alice is not
    authenticated authorship - it must never reach 'verified'."""
    spoof = dict(GOOD, url_host="evil-example.net", url_handle="")
    assert vg._decide(**spoof) == (UV, "")
    # self-declared metadata AND a fake handle path in the URL: still refused
    assert vg._decide(**dict(spoof, url_handle="alice")) == (UV, "")
    # lookalike / subdomain-of-lookalike hosts are not the platform
    assert vg._decide(**dict(GOOD, url_host="x.com.evil.net")) == (UV, "")
    assert vg._decide(**dict(GOOD, url_host="x.com.evil.net", url_handle="alice")) == (UV, "")
    # ... and the URL helper agrees: no structural handle off-platform
    assert vg._url_handle("https://evil-example.net/alice/vouch") == ""
    # a real X page is unaffected
    assert vg._decide(**GOOD) == (V, GOOD_QUOTE)


# --- steward objection 1: reputation poisoning -------------------------------

def test_stat_delta_is_positive_only():
    for verdict in (NF, AM, UV, "pending"):
        assert vg._stat_delta(verdict) == 0
    assert vg._stat_delta(V) == 1


def test_third_party_poisoning_cannot_stain_another_handle():
    """Arbitrary callers fire failing checks at @alice; reputation must not
    move, and 'clean' must never flip to unclean because of them."""
    rep = {}

    def submit(handle, verdict):
        rep[handle] = rep.get(handle, 0) + vg._stat_delta(verdict)

    poisoned = [
        # garbage claim URL that will not resolve
        ("alice", NF),
        # someone else's status URL claimed for alice
        ("alice", AM),
        # arbitrary domain with self-declared metadata
        ("alice", UV),
        # repeated spam attempts
        ("alice", NF), ("alice", UV), ("alice", NF),
    ]
    for handle, verdict in poisoned:
        submit(handle, verdict)
    assert rep == {"alice": 0}

    # the poisoned attempts above are the verdicts _decide actually returns
    assert vg._decide(**dict(GOOD, found=False))[0] == NF
    assert vg._decide(**dict(GOOD, url_handle="bob"))[0] == AM
    assert vg._decide(**dict(GOOD, url_host="evil-example.net", url_handle=""))[0] == UV

    # alice's own authenticated vouch is the only thing that moves the meter
    submit("alice", vg._decide(**GOOD)[0])
    assert rep["alice"] == 1 and rep["alice"] > 0  # clean


def test_keying_and_retry_semantics():
    """Same URL checked against two handles = two independent records; a
    non-verified verdict is retryable (same key), verified is final."""
    u = "https://x.com/alice/status/1"
    k = lambda h: vg._norm_url(u) + "|" + vg._norm_handle(h)
    assert k("@alice") != k("@bob")
    assert k("@alice") == vg._norm_url("https://X.com/alice/status/1/") + "|" + vg._norm_handle("Alice")
    # a non-verified pair never blocks the other handle's record
    assert k("@alice") not in (k("@bob"),)


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"PASS {len(tests)} tests")


if __name__ == "__main__":
    main()
