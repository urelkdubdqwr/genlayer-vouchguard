# { "Depends": "py-genlayer:test" }

import json
from dataclasses import dataclass
from genlayer import *


@allow_storage
@dataclass
class HandleStat:
    handles_checked: u256  # total checks submitted against this handle
    verified: u256  # how many claims resolved to "verified"


@allow_storage
@dataclass
class Check:
    claim_url: str
    expected_handle: str
    verdict: str  # "verified" | "not_found"
    quote: str  # exact quote from the page supporting the verdict


class VouchGuard(gl.Contract):
    """On-chain vouch verification.

    Anyone can submit a claim URL (a public page that supposedly contains a
    vouch/endorsement post, e.g. an X status page) plus the handle that is
    expected to have made it. Validators fetch the page (nondeterministic
    web access), an LLM extracts the evidence, and the result is agreed on
    with GenLayer's equivalence principle. The verdict becomes immutable,
    publicly queryable on-chain history.
    """

    checks: TreeMap[str, Check]
    stats: TreeMap[str, HandleStat]
    total: u256

    def __init__(self):
        pass

    def _analyze(self, claim_url: str, expected_handle: str) -> dict:
        def run() -> str:
            page = gl.get_webpage(claim_url, mode="text")

            task = f"""
You are verifying a public endorsement ("vouch").
Expected author handle: {expected_handle}

Analyze the following page content and decide whether it contains a post
written by @{expected_handle} that publicly vouches for, endorses or
attests to someone's trustworthiness.

Page content:
{page}

Respond in JSON:
{{
    "found": bool,      // true only if the author handle matches AND text is a vouch/endorsement
    "quote": str        // the exact sentence that proves it, or "" if not found
}}
It is mandatory that you respond only using the JSON format above, nothing
else. Don't include any other words or characters, your output must be only
JSON without any formatting prefix or suffix. This result should be
perfectly parsable by a JSON parser without errors.
        """
            result = gl.exec_prompt(task).replace("```json", "").replace("```", "")
            return json.dumps(json.loads(result), sort_keys=True)

        return json.loads(gl.eq_principle_strict_eq(run))

    @gl.public.write
    def submit_check(self, claim_url: str, expected_handle: str) -> None:
        if claim_url in self.checks:
            raise Exception("Claim already checked")
        self.checks[claim_url] = Check(
            claim_url=claim_url,
            expected_handle=expected_handle,
            verdict="pending",
            quote="",
        )
        res = self._analyze(claim_url, expected_handle)
        c = self.checks[claim_url]
        c.verdict = "verified" if res.get("found") else "not_found"
        c.quote = str(res.get("quote", ""))[:1000]
        self.total += 1
        s = self.stats.get_or_insert_default(expected_handle.lower())
        s.handles_checked += 1
        if c.verdict == "verified":
            s.verified += 1

    @gl.public.view
    def get_check(self, claim_url: str) -> dict:
        if claim_url not in self.checks:
            raise Exception("Unknown claim")
        c = self.checks[claim_url]
        return {
            "claim_url": c.claim_url,
            "expected_handle": c.expected_handle,
            "verdict": c.verdict,
            "quote": c.quote,
        }

    @gl.public.view
    def total_checks(self) -> int:
        return self.total

    @gl.public.view
    def get_handle_stats(self, handle: str) -> dict:
        s = self.stats.get(handle.lower(), HandleStat(0, 0))
        return {
            "handle": handle.lower(),
            "checks": s.handles_checked,
            "verified": s.verified,
            "clean": s.handles_checked > 0 and s.verified == s.handles_checked,
        }
