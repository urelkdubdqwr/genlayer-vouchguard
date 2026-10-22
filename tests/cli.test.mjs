import { test } from "node:test";
import assert from "node:assert/strict";
import { parseArgs, normalizeHandle } from "../cli/lib.mjs";

test("normalizeHandle strips @ and lowercases", () => {
  assert.equal(normalizeHandle("@Kstellar"), "kstellar");
  assert.equal(normalizeHandle("  @Onar "), "onar");
  assert.equal(normalizeHandle(""), "");
});

test("parseArgs: check requires url + handle", () => {
  const a = parseArgs(["0x" + "ab".repeat(20), "check", "https://x.com/h/status/1", "@h"]);
  assert.equal(a.cmd, "check");
  assert.equal(a.url, "https://x.com/h/status/1");
  assert.equal(a.handle, "@h");
  assert.throws(() => parseArgs(["0x" + "ab".repeat(20), "check", "https://x.com/h/status/1"]));
});

test("parseArgs: read requires url only", () => {
  const a = parseArgs(["0x" + "ab".repeat(20), "read", "https://x.com/h/status/1"]);
  assert.equal(a.cmd, "read");
  assert.throws(() => parseArgs(["0x" + "ab".repeat(20), "read"]));
});

test("parseArgs: rejects bad contract address and unknown cmd", () => {
  assert.throws(() => parseArgs(["nope", "read", "x"]));
  assert.throws(() => parseArgs(["0x" + "ab".repeat(20), "yolo"]));
});
