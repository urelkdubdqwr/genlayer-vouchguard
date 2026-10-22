<img src="assets/header.svg" alt="VouchGuard — on-chain vouch verification" width="100%">

**[urelkdubdqwr](https://github.com/urelkdubdqwr)** · [studiopinggirkasur.xyz](https://studiopinggirkasur.xyz/)

**Vouches you can't fake — two strangers, one bond, settled by consensus instead of vibes.**

## What it is

VouchGuard is a GenLayer Intelligent Contract that verifies public endorsements on-chain. You hand it a claim URL (a public page that supposedly contains a vouch, e.g. an X status) plus the handle that supposedly wrote it. Validators fetch the page, an LLM pulls out the sentence that proves it, and the result is agreed through GenLayer's equivalence principle.

The verdict lands in contract state as immutable history: no screenshots to edit, no trust-me-bro, no moderator deciding what is real. Anyone can read it back forever, and every checked handle accumulates an on-chain reputation.

## How it works

![VouchGuard architecture](assets/ecosystem.png)

- `submit_check(url, handle)` — one write. The contract records the claim, then runs the nondeterministic block: `gl.get_webpage(url, mode="text")` pulls the live page.
- An LLM prompt asks one question only: does this page contain a post by `@handle` that vouches for, endorses or attests to someone? It answers strict JSON — `found` plus the `quote` that proves it.
- `gl.eq_principle_strict_eq` makes validators run the same code and compare the normalized JSON, so the verdict is consensus output, not one node's opinion.
- The verdict (`verified` / `not_found`) plus the quoted evidence is stored under the claim URL. Re-checking the same URL is rejected — one claim, one immutable result.
- Every check also bumps a per-handle aggregate, so `get_handle_stats(handle)` answers "has this handle ever faked a vouch?" without re-fetching anything.

## Quickstart

```bash
npm install                    # genlayer-js (dev dep)
npm test                       # CLI unit tests (node:test, zero deps)

export GENLAYER_KEY_FILE=~/.genlayer/key    # hex private key file, needed for writes

# submit a check: writes to the chain and waits for ACCEPTED
node cli/vouchguard.mjs 0x<contract> check https://x.com/someone/status/123 someone

# read a settled verdict, or a handle's reputation (free calls)
node cli/vouchguard.mjs 0x<contract> read  https://x.com/someone/status/123
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
| `assets/` | Header banner and architecture diagram sources |

## License

MIT — see [LICENSE](LICENSE).

*Worked from the edge of the bed. → [studiopinggirkasur.xyz](https://studiopinggirkasur.xyz/)*
