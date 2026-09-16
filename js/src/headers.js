/**
 * Small response header helpers shared by the middleware.
 */

/**
 * Add a field name to `Vary` without repeating it.
 *
 * Both content negotiation and CORS need to extend `Vary`; a plain `res.set`
 * from either of them would silently drop the other one's contribution.
 *
 * @param {object} res - Express response
 * @param {string} field - Header field name to add
 * @returns {void}
 */
export function appendVary(res, field) {
  const current = res.getHeader("Vary");
  const existing =
    current === undefined
      ? []
      : String(current)
          .split(",")
          .map((entry) => entry.trim())
          .filter(Boolean);

  if (existing.some((entry) => entry.toLowerCase() === field.toLowerCase())) {
    return;
  }
  res.set("Vary", [...existing, field].join(", "));
}
