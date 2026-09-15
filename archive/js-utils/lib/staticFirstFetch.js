// lib/staticFirstFetch | "Static file first, remote fallback" read strategy for
// serverless handlers: read a pre-generated JSON file if present, otherwise call
// a remote fetcher (and optionally require an API key only on the fallback path).
// source: kuhwa api/calendar.js (readStaticYear + NEIS fallback)

const fs = require("fs");

/**
 * Read JSON from disk, returning null (instead of throwing) if missing/invalid.
 *
 * @param {string} filePath Absolute path to the JSON file.
 * @param {(data: any) => any} [pickFn] Optional selector applied to the parsed JSON
 *   (defaults to the identity function).
 * @returns {any|null}
 */
function readStaticJson(filePath, pickFn = (data) => data) {
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    const data = JSON.parse(raw);
    const picked = pickFn(data);
    return picked ?? null;
  } catch {
    return null;
  }
}

/**
 * Resolve data via "static file first, remote fetch as fallback".
 *
 * @param {string} filePath Absolute path to the pre-generated static JSON file.
 * @param {() => Promise<any>} fetchRemote Called only if the static file is
 *   missing/unreadable/empty.
 * @param {(data: any) => any} [pickFn] Optional selector applied to the parsed
 *   static JSON.
 * @returns {Promise<any>}
 */
async function staticFirstFetch(filePath, fetchRemote, pickFn = (data) => data) {
  const staticData = readStaticJson(filePath, pickFn);
  if (staticData) return staticData;
  return fetchRemote();
}

module.exports = { readStaticJson, staticFirstFetch };
