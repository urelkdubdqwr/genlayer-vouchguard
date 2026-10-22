// Shared, testable helpers for the VouchGuard CLI.
export function parseArgs(argv) {
  const [address, cmd, ...rest] = argv;
  if (!address || !/^0x[0-9a-fA-F]{40}$/.test(address)) throw new Error("contract address must be 0x + 40 hex chars");
  if (cmd === "check") {
    if (rest.length < 2) throw new Error("check needs <claim_url> <handle>");
    return { address, cmd, url: rest[0], handle: rest[1] };
  }
  if (cmd === "read") {
    if (rest.length < 1) throw new Error("read needs <claim_url>");
    return { address, cmd, url: rest[0] };
  }
  if (cmd === "stats") {
    if (rest.length < 1) throw new Error("stats needs <handle>");
    return { address, cmd, handle: rest[0] };
  }
  throw new Error(`unknown command: ${cmd}`);
}

export function normalizeHandle(h) {
  return String(h || "").trim().replace(/^@/, "").toLowerCase();
}
