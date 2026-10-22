#!/usr/bin/env node
// VouchGuard client — backend app logic talking to the deployed Intelligent Contract.
// Usage: node cli/vouchguard.mjs <contract> check <claim_url> <handle>
//        node cli/vouchguard.mjs <contract> read  <claim_url>
import { readFileSync } from "node:fs";
import { createClient, createAccount } from "genlayer-js";

const BRADBURY = {
  id: 4221,
  name: "GenLayer Bradbury Testnet",
  nativeCurrency: { name: "GEN", symbol: "GEN", decimals: 18 },
  rpcUrls: { default: { http: ["https://rpc-bradbury.genlayer.com"] } },
};

const [address, cmd, ...rest] = process.argv.slice(2);
if (!address || !cmd) {
  console.error("usage: vouchguard.mjs <contract> check <url> <handle> | read <url>");
  process.exit(1);
}

const key = readFileSync(
  process.env.GENLAYER_KEY_FILE || `${process.env.HOME}/wallets/key227`,
  "utf8",
).trim();
const account = createAccount(key.startsWith("0x") ? key : `0x${key}`);
const client = createClient({ chain: BRADBURY, account });

if (cmd === "read") {
  const res = await client.readContract({
    address,
    functionName: "get_check",
    args: [rest[0]],
  });
  console.log(JSON.stringify(res, null, 2));
} else if (cmd === "check") {
  const tx = await client.writeContract({
    address,
    functionName: "submit_check",
    args: [rest[0], rest[1]],
  });
  console.log("tx:", tx);
  const receipt = await client.waitForTransactionReceipt({ hash: tx, status: "ACCEPTED", retries: 200 });
  console.log("result:", JSON.stringify(receipt.consensus_data?.leader_receipt?.[0]?.execution_result));
  console.log(JSON.stringify(await client.readContract({ address, functionName: "get_check", args: [rest[0]] }), null, 2));
} else {
  console.error(`unknown command: ${cmd}`);
  process.exit(1);
}
