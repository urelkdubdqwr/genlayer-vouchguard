// Shared, testable helpers for the VouchGuard CLI.
export function parseArgs(argv) {
  const [address, cmd, ...rest] = argv;
  if (!address || !/^0x[0-9a-fA-F]{40}$/.test(address)) throw new Error("contract address must be 0x + 40 hex chars");
  if (cmd === "check") {
    if (rest.length < 2) throw new Error("check needs <claim_url> <handle>");
    return { address, cmd, url: rest[0], handle: rest[1] };
  }
  if (cmd === "read") {
    if (rest.length < 2) throw new Error("read needs <claim_url> <handle>");
    return { address, cmd, url: rest[0], handle: rest[1] };
  }
  if (cmd === "stats") {
    if (rest.length < 1) throw new Error("stats needs <handle>");
    return { address, cmd, handle: rest[0] };
  }
  throw new Error(`unknown command: ${cmd}`);
}

// Mirrors the contract's _norm_handle: strip @, lowercase, profile URLs -> last path segment.
export function normalizeHandle(h) {
  let s = String(h || "").trim().toLowerCase();
  if (s.includes("/")) s = s.replace(/\/+$/, "").split("/").pop();
  return s.replace(/^@/, "");
}

// Mirrors the contract's _url_handle: handle carried by an X/Twitter URL path.
export function urlHandle(url) {
  let u = String(url || "").trim().toLowerCase();
  u = u.replace(/^https?:\/\//, "").replace(/^www\./, "");
  const [host, ...segs] = u.split("/");
  if (!["x.com", "twitter.com", "mobile.x.com", "mobile.twitter.com"].includes(host)) return "";
  if (!segs.length) return "";
  const first = segs[0];
  if (!first || ["i", "home", "explore", "search", "hashtag", "intent"].includes(first)) return "";
  return first;
}
