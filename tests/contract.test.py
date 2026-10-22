#!/usr/bin/env python3
"""Unit tests for VouchGuard deterministic helpers (no GenVM needed).

Stubs the `genlayer` module so contracts/vouchguard.py imports cleanly,
then asserts the pure functions that carry the security decisions.
Run: python3 tests/contract.test.py
"""
import sys, types, pathlib
from dataclasses import dataclass as _dc

root = pathlib.Path(__file__).resolve().parent.parent

stub = types.ModuleType("genlayer")
def _allow_storage(cls):
    return cls
stub.allow_storage = _allow_storage
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


stub.gl = _GL
sys.modules["genlayer"] = stub
sys.path.insert(0, str(root / "contracts"))

import vouchguard as vg  # noqa: E402


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
    # non-X hosts carry no structural handle
    assert vg._url_handle("https://blog.example.com/vouch") == ""
    # non-profile paths are not handles
    assert vg._url_handle("https://x.com/i/web/status/1") == ""
    assert vg._url_handle("https://x.com/hashtag/foo") == ""


def test_quote_in_page():
    page = "Vouching for @dev: I have worked with Dev for 2 years, solid engineer."
    assert vg._quote_in_page("I have worked with Dev for 2 years", page)
    assert vg._quote_in_page("I HAVE WORKED   WITH dev", page)
    # hallucinated / reformulated quote must FAIL
    assert not vg._quote_in_page("Dev is the best dev ever", page)
    assert not vg._quote_in_page("", page)
    # quote spanning the full text
    assert vg._quote_in_page(page, page)


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"PASS {len(tests)} tests")


if __name__ == "__main__":
    main()
