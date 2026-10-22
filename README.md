<img src="assets/header.svg" alt="VouchGuard — on-chain vouch verification" width="100%">

**[urelkdubdqwr](https://github.com/urelkdubdqwr)** · [studiopinggirkasur.xyz](https://studiopinggirkasur.xyz/)

**Vouches you can't fake — two strangers, one bond, settled by consensus instead of vibes.**

## What it is

VouchGuard is a GenLayer Intelligent Contract that verifies public endorsements on-chain. You hand it a claim URL (a public page that supposedly contains a vouch, e.g. an X status) plus the handle that supposedly wrote it. Validators fetch the page, an LLM pulls out the sentence that proves it, and the result is agreed through GenLayer's equivalence principle.

The verdict lands in contract state as immutable history: no screenshots to edit, no trust-me-bro, no moderator deciding what is real. Anyone can read it back forever, and every checked handle accumulates an on-chain reputation.

## How it works

![VouchGuard architecture](assets/ecosystem.png)

- `submit_check(url, handle)` — one write, keyed by **(normalized URL, handle)**.
  The same page can be checked against different handles independently, and a
  check that came back `not_found` / `author_mismatch` / `unverifiable` can be
  retried (each attempt is counted). Only a **`verified` verdict is final** —
  so a first caller can never permanently bind a page to the wrong handle.
- **Authorship is authenticated structurally, in two layers:**
  1. the handle embedded in the page URL (`x.com/<handle>/status/...`) must
     equal the claimed handle;
  2. the author the page's *own metadata* attributes the post to (`<title>`
     "… on X", `twitter:creator` / `author` meta, profile & JSON-LD links) is
     extracted by an LLM **independently of the claim** and must also equal the
     claimed handle.
  A mismatch stores an `author_mismatch` verdict as on-chain evidence of the
  failed binding; a page with no authorship evidence at all is `unverifiable`.
- **The quote must be in the page.** The contract renders the page twice
  (`mode="html"` for metadata, `mode="text"` for content). The LLM that flags a
  vouch must return the exact supporting sentence, and a deterministic
  containment check (`quote ∈ fetched text`, case/whitespace-insensitive) has
  to pass — a hallucinated or reformulated quote can never produce `verified`.
- `gl.eq_principle_strict_eq` makes validators run the same code and agree on
  the normalized JSON (author, found, quote, `quote_in_page`), so the verdict
  is consensus output, not one node's opinion.
- Verdicts: `verified` / `not_found` / `author_mismatch` / `unverifiable`.
  Every attempt also bumps a per-handle aggregate, so
  `get_handle_stats(handle)` answers "has this handle ever faked a vouch?"

## v3 security model (what changed vs v2)

| Steward objection (v2 rejection) | v3 mechanism |
| --- | --- |
| URL-only uniqueness lets the first caller permanently bind a page to the wrong handle | results keyed by `(normalized URL, handle)`; only *verified* verdicts are immutable, everything else is retryable and attempt-counted |
| contract does not authenticate authorship | dual structural check: URL-path handle + page-metadata author extracted independently of the claim; either mismatch → `author_mismatch`, no metadata → `unverifiable` |
| extracted quote is not verified against the fetched page | deterministic `quote ∈ page_text` containment gate before any verdict can become `verified` |

Decision logic lives in one pure, unit-tested function (`_decide`), and the
same rules are mirrored client-side in `cli/lib.mjs` so bad claims are refused
before gas is spent.

## Quickstart

```bash
npm install                    # genlayer-js (dev dep)
npm test                       # CLI unit tests (node:test, zero deps)
python3 tests/contract.test.py # contract helper + verdict-gate tests (no GenVM needed)

export GENLAYER_KEY_FILE=~/.genlayer/key    # hex private key file, needed for writes

# submit a check: writes to the chain and waits for ACCEPTED
node cli/vouchguard.mjs 0x<contract> check https://x.com/someone/status/123 someone

# read a settled verdict for one (url, handle) pair, or a handle's reputation
node cli/vouchguard.mjs 0x<contract> read  https://x.com/someone/status/123 someone
node cli/vouchguard.mjs 0x<contract> stats someone
```

No build step for the UI: open `ui/index.html`, paste the contract address, claim URL and handle — it reads the chain through `genlayer-js` in the browser.

Deploy the contract with the GenLayer CLI:

```bash
genlayer deploy --contract contracts/vouchguard.py
```

## What's inside

| Path | What it does |
| --- | --- |
| `contracts/vouchguard.py` | The Intelligent Contract: web fetch, LLM extraction, equivalence principle, verdicts, handle stats |
| `cli/vouchguard.mjs` | Node client (genlayer-js): `check` / `read` / `stats` against the deployed contract |
| `cli/lib.mjs` | Argument parsing and handle normalization (unit tested) |
| `ui/index.html` | Single-file web UI, reads verdicts and reputation from the chain |
| `tests/cli.test.mjs` | `node --test` suite for the CLI helpers |
| `tests/contract.test.py` | verdict-gate + helper tests for the contract (auth rules are pure and testable) |
| `assets/` | Header banner and architecture diagram sources |

## License

MIT — see [LICENSE](LICENSE).

*Worked from the edge of the bed. → [studiopinggirkasur.xyz](https://studiopinggirkasur.xyz/)*
