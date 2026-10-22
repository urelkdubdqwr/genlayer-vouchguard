# VouchGuard

On-chain vouch verification for GenLayer. Post a proof link, get an immutable verdict.

## What it does

Vouch checking is manual today: someone posts "I vouch for X" somewhere, and everyone
else has to open the link and eyeball it. VouchGuard turns that into a one-command
consensus check.

1. Call `submit_check(claim_url, expected_handle)` — e.g. an X/Twitter status URL plus
   the handle that supposedly vouched.
2. Validators fetch the page (`gl.get_webpage`, GenLayer nondeterministic web access),
   an LLM decides whether that handle actually wrote an endorsement there, and the
   result is agreed with the equivalence principle (`gl.eq_principle_strict_eq`).
3. The verdict (`verified` / `not_found`) plus the exact supporting quote is stored
   on-chain: immutable, publicly queryable history.

Because the check runs through GenLayer consensus, no single operator can fake the
verdict.

## Repo layout

- `contracts/vouchguard.py` — the Intelligent Contract
- `cli/vouchguard.mjs` — backend client (Node + `genlayer-js`): submit checks, read verdicts, handle stats
- `ui/index.html` — single-file web UI: paste a claim URL + handle, read the on-chain verdict
- `tests/cli.test.mjs` — CLI unit tests (`npm test`, `node:test`, zero deps)

### v2: handle reputation

Every check updates an on-chain aggregate per handle — `get_handle_stats(handle)`
returns total checks, verified count and a `clean` flag. Communities can ask the
chain "has this handle ever faked a vouch?" instead of re-checking each claim.

## Deployed

- Network: Bradbury Testnet (chain id 4221, `https://rpc-bradbury.genlayer.com`)
- Contract address: see `DEPLOYMENT.md`

## Usage

```bash
npm install

# submit a check (consensus transaction)
node cli/vouchguard.mjs <contract_address> check https://x.com/handle/status/123 expected_handle

# read a stored verdict (free call)
node cli/vouchguard.mjs <contract_address> read https://x.com/handle/status/123
```

`GENLAYER_KEY_FILE` (default `~/wallets/key227`) is the signing key the client reads.

## Deploy

```bash
genlayer network set testnet-bradbury
genlayer deploy --contract contracts/vouchguard.py --account <account> --password <pw>
```

## License

MIT
