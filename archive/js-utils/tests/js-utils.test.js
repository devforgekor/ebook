const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");

const { fetchAllPages } = require("../lib/paginate");
const { mergeByKey } = require("../lib/mergeByKey");
const { staticFirstFetch, readStaticJson } = require("../lib/staticFirstFetch");
const { validatePattern } = require("../lib/validateQueryParam");

test("fetchAllPages collects rows across parallel pages", async () => {
  const pages = {
    1: { totalCount: 5, rows: [1, 2] },
    2: { totalCount: 5, rows: [3, 4] },
    3: { totalCount: 5, rows: [5] },
  };
  const rows = await fetchAllPages(async (pIndex) => pages[pIndex], 2);
  assert.deepEqual(rows.sort(), [1, 2, 3, 4, 5]);
});

test("fetchAllPages handles a single page", async () => {
  const rows = await fetchAllPages(async () => ({ totalCount: 2, rows: [1, 2] }), 10);
  assert.deepEqual(rows, [1, 2]);
});

test("mergeByKey dedupes and accumulates a field", () => {
  const rows = [
    { date: "20260101", name: "A", tag: "초" },
    { date: "20260101", name: "A", tag: "중" },
    { date: "20260102", name: "B", tag: "고" },
  ];
  const merged = mergeByKey(
    rows,
    (r) => `${r.date}_${r.name}`,
    (r) => ({ date: r.date, name: r.name, tags: [r.tag].filter(Boolean) }),
    { accumulateField: "tags", accumulateFn: (r) => r.tag }
  );
  assert.equal(merged.length, 2);
  assert.deepEqual(merged[0].tags, ["초", "중"]);
  assert.deepEqual(merged[1].tags, ["고"]);
});

test("staticFirstFetch prefers the static file when present", async () => {
  const tmpFile = path.join(os.tmpdir(), `js-utils-test-${Date.now()}.json`);
  fs.writeFileSync(tmpFile, JSON.stringify({ events: [{ ok: true }] }));
  let remoteCalled = false;
  const data = await staticFirstFetch(
    tmpFile,
    async () => {
      remoteCalled = true;
      return [{ ok: false }];
    },
    (json) => json.events
  );
  assert.deepEqual(data, [{ ok: true }]);
  assert.equal(remoteCalled, false);
  fs.unlinkSync(tmpFile);
});

test("staticFirstFetch falls back to remote when file is missing", async () => {
  const data = await staticFirstFetch(
    "/nonexistent/path/2099.json",
    async () => [{ fallback: true }],
    (json) => json.events
  );
  assert.deepEqual(data, [{ fallback: true }]);
});

test("readStaticJson returns null for missing file", () => {
  assert.equal(readStaticJson("/nonexistent/path.json"), null);
});

test("validatePattern rejects invalid input with 400", () => {
  let statusCode = null;
  let body = null;
  const res = {
    status(code) { statusCode = code; return this; },
    json(payload) { body = payload; },
  };
  const ok = validatePattern(res, "abcd", /^\d{4}$/, "bad year");
  assert.equal(ok, false);
  assert.equal(statusCode, 400);
  assert.deepEqual(body, { error: "bad year" });
});

test("validatePattern accepts valid input without touching res", () => {
  let called = false;
  const res = { status() { called = true; return this; }, json() { called = true; } };
  const ok = validatePattern(res, "2026", /^\d{4}$/, "bad year");
  assert.equal(ok, true);
  assert.equal(called, false);
});
