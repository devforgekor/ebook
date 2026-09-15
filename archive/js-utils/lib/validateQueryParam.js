// lib/validateQueryParam | Validate a request query parameter against a regex
// pattern and short-circuit an HTTP response (Express/Vercel-style res object)
// with a 400 error when it doesn't match.
// source: kuhwa api/schedule.js (year 파라미터 4자리 숫자 검증)

/**
 * Validate `value` against `pattern`; if invalid, writes a 400 JSON error to
 * `res` and returns false. Otherwise returns true and leaves `res` untouched.
 *
 * @param {import('http').ServerResponse & { status: Function, json: Function }} res
 *   Vercel/Express-style response object (must expose `.status(code).json(body)`).
 * @param {string} value Value to validate (e.g. `req.query.year`).
 * @param {RegExp} pattern Regex the value must fully match.
 * @param {string} errorMessage Message returned in the 400 response body.
 * @returns {boolean} true if valid, false if a 400 response was already sent.
 */
function validatePattern(res, value, pattern, errorMessage) {
  if (!pattern.test(value)) {
    res.status(400).json({ error: errorMessage });
    return false;
  }
  return true;
}

module.exports = { validatePattern };
