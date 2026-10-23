#!/usr/bin/env node
// VouchGuard client — backend app logic talking to the deployed Intelligent Contract.
// Usage: node cli/vouchguard.mjs <contract> check <claim_url> <handle>
//        node cli/vouchguard.mjs <contract> read  <claim_url> <handle>
import { readFileSync } from "node:fs";
import { createClient, createAccount } from "genlayer-js";
import { studionet, testnetBradbury } from "genlayer-js/chains";
import { parseArgs, normalizeHandle, urlHandle } from "./lib.mjs";

const CHAINS = { studio: studionet, bradbury: testnetBradbury };
const chain = CHAINS[process.env.VOUCHGUARD_CHAIN || "bradbury"];

let args;
try {
  args = parseArgs(process.argv.slice(2));
} catch (e) {
  console.error(`usage: vouchguard.mjs <contract> check <url> <handle> | read <url> <handle> | stats <handle>\n${e.message}`);
  process.exit(1);
}
const { address, cmd } = args;

const keyFile = process.env.GENLAYER_KEY_FILE;
if (!keyFile) {
  console.error("set GENLAYER_KEY_FILE to a hex private key file");
  process.exit(1);
}
const key = readFileSync(keyFile, "utf8").trim();
const account = createAccount(key.startsWith("0x") ? key : `0x${key}`);
const client = createClient({ chain, account });

const handle = normalizeHandle(args.handle);
// Client-side mirror of the contract's verdict gate: refuse to even submit a
// claim whose authorship cannot be authenticated before spending gas.
const uh = urlHandle(args.url);
// Platform syndication CDN: the platform's own tweet JSON (fetchable where the
// x.com HTML page 403s runners). Authorship is authenticated from the payload.
let synd = false;
try {
  const u = new URL(args.url);
  synd = /(^|\.)cdn\.syndication\.twimg\.com$/i.test(u.hostname)
    && u.pathname.includes("tweet-result") && u.searchParams.has("id");
} catch {}
if (cmd === "check" && !synd) {
  if (!uh) {
    console.error("unverifiable: authorship must be authenticated on x.com/twitter.com (or a platform syndication URL) — metadata on an arbitrary domain can never verify");
    process.exit(2);
  }
  if (uh !== handle) {
    console.error(`author_mismatch: URL belongs to @${uh}, claim says @${handle}`);
    process.exit(2);
  }
}

if (cmd === "read") {
  const res = await client.readContract({
    address,
    functionName: "get_check",
    args: [args.url, handle],
  });
  console.log(JSON.stringify(res, null, 2));
} else if (cmd === "stats") {
  console.log(JSON.stringify(await client.readContract({ address, functionName: "get_handle_stats", args: [handle] }), null, 2));
} else if (cmd === "check") {
  const tx = await client.writeContract({
    address,
    functionName: "submit_check",
    args: [args.url, handle],
  });
  console.log("tx:", tx);
  const receipt = await client.waitForTransactionReceipt({ hash: tx, status: "ACCEPTED", retries: 200 });
  console.log("result:", JSON.stringify(receipt.consensus_data?.leader_receipt?.[0]?.execution_result));
  console.log(JSON.stringify(await client.readContract({ address, functionName: "get_check", args: [args.url, handle] }), null, 2));
} else {
  console.error(`unknown command: ${cmd}`);
  process.exit(1);
}
