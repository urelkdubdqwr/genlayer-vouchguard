import { test } from "node:test";
import assert from "node:assert/strict";
import { parseArgs, normalizeHandle, urlHandle } from "../cli/lib.mjs";

const addr = "0x" + "ab".repeat(20);

test("normalizeHandle strips @, lowercases, and reduces profile URLs", () => {
  assert.equal(normalizeHandle("@Kstellar"), "kstellar");
  assert.equal(normalizeHandle("  @Onar "), "onar");
  assert.equal(normalizeHandle("https://x.com/Onar/"), "onar");
  assert.equal(normalizeHandle(""), "");
});

test("urlHandle reads the handle carried by a status/profile URL", () => {
  assert.equal(urlHandle("https://x.com/alice/status/1"), "alice");
  assert.equal(urlHandle("https://twitter.com/Bob/status/9"), "bob");
  assert.equal(urlHandle("https://x.com/carol"), "carol");
  assert.equal(urlHandle("https://blog.example.com/vouch"), "");
  assert.equal(urlHandle("https://x.com/i/web/status/1"), "");
});

test("parseArgs: check requires url + handle", () => {
  const a = parseArgs([addr, "check", "https://x.com/h/status/1", "@h"]);
  assert.equal(a.cmd, "check");
  assert.equal(a.url, "https://x.com/h/status/1");
  assert.equal(a.handle, "@h");
  assert.throws(() => parseArgs([addr, "check", "https://x.com/h/status/1"]));
});

test("parseArgs: read requires url + handle (verdicts are per (url, handle))", () => {
  const a = parseArgs([addr, "read", "https://x.com/h/status/1", "@h"]);
  assert.equal(a.cmd, "read");
  assert.throws(() => parseArgs([addr, "read", "https://x.com/h/status/1"]));
  assert.throws(() => parseArgs([addr, "read"]));
});

test("parseArgs: rejects bad contract address and unknown cmd", () => {
  assert.throws(() => parseArgs(["nope", "read", "x", "y"]));
  assert.throws(() => parseArgs([addr, "yolo"]));
});

// The client mirrors the contract's authorship gate before spending gas:
// the URL must live on the X/Twitter platform AND carry the claimed handle.
test("client-side authorship gate", () => {
  const uh = urlHandle("https://x.com/bob/status/1");
  assert.notEqual(uh, normalizeHandle("@alice"));
  assert.equal(uh, normalizeHandle("@bob"));
  // host gate: arbitrary (or lookalike) domains can never authenticate
  assert.equal(urlHandle("https://evil-example.net/alice/vouch"), "");
  assert.equal(urlHandle("https://x.com.evil.net/alice/status/1"), "");
});
