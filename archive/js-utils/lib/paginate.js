// lib/paginate | Generic paginated-API collector: fetch page 1 to learn totalCount,
// then fetch remaining pages in parallel and concatenate rows.
// source: kuhwa api/schedule.js, scripts/fetch-schedule.js (NEIS SchoolSchedule pagination)

/**
 * Collect all rows from a paginated API.
 *
 * @param {(pageIndex: number) => Promise<{ totalCount: number, rows: any[] }>} fetchPage
 *   Function that fetches a single page (1-based index) and returns the total
 *   item count (as reported by the API) plus that page's rows.
 * @param {number} pageSize
 *   Number of items per page, used to compute how many pages remain.
 * @returns {Promise<any[]>} All rows across all pages, in page order for page 1,
 *   then unordered relative to each other for the remaining pages (they are
 *   fetched in parallel).
 */
async function fetchAllPages(fetchPage, pageSize) {
  const first = await fetchPage(1);
  const rows = [...first.rows];
  const totalPages = Math.ceil(first.totalCount / pageSize);

  if (totalPages > 1) {
    const remainingPages = await Promise.all(
      Array.from({ length: totalPages - 1 }, (_, i) => fetchPage(i + 2))
    );
    for (const page of remainingPages) {
      rows.push(...page.rows);
    }
  }

  return rows;
}

module.exports = { fetchAllPages };
