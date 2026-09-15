// lib/mergeByKey | Deduplicate a list of raw items into objects keyed by a derived
// string key, optionally accumulating a secondary field into an array on repeats.
// source: kuhwa api/schedule.js, api/calendar.js (date+event-name merge, course accumulation)

/**
 * Merge/deduplicate raw rows by a derived key.
 *
 * @param {any[]} rows Raw items to merge.
 * @param {(row: any) => string} keyFn Derives the dedupe key for a row.
 * @param {(row: any) => any} mapFn Maps a row to the object stored on first sight.
 * @param {{
 *   accumulateField?: string,
 *   accumulateFn?: (row: any) => any,
 * }} [options]
 *   accumulateField: name of an array field on the mapped object to push into on
 *   repeat keys (skips falsy/duplicate values). accumulateFn: derives the value to
 *   push (defaults to accumulateField itself via mapFn's output shape).
 * @returns {any[]} Merged objects, insertion-ordered.
 */
function mergeByKey(rows, keyFn, mapFn, options = {}) {
  const { accumulateField, accumulateFn } = options;
  const merged = new Map();

  for (const row of rows) {
    const key = keyFn(row);
    if (!merged.has(key)) {
      merged.set(key, mapFn(row));
      continue;
    }
    if (accumulateField && accumulateFn) {
      const existing = merged.get(key);
      const value = accumulateFn(row);
      if (value && Array.isArray(existing[accumulateField]) && !existing[accumulateField].includes(value)) {
        existing[accumulateField].push(value);
      }
    }
  }

  return Array.from(merged.values());
}

module.exports = { mergeByKey };
