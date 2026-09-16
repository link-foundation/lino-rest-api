/**
 * Collection envelope, in-memory query execution and RFC 8288 link headers
 * (specification §6).
 */

/**
 * Test whether an item satisfies every filter.
 *
 * A filter whose value is a list matches when the item field equals any member,
 * which is what repeated query parameters (`?tag=a&tag=b`) mean.
 *
 * @param {object} item - Candidate item
 * @param {object} filters - Field filters
 * @returns {boolean} True when the item matches
 */
export function matchesFilters(item, filters) {
  return Object.entries(filters).every(([field, expected]) => {
    const actual = item?.[field];
    if (Array.isArray(expected)) {
      return expected.some((candidate) => candidate === actual);
    }
    return actual === expected;
  });
}

/**
 * Compare two values in a total order that works across LINO scalar types.
 *
 * @param {*} left - First value
 * @param {*} right - Second value
 * @returns {number} Negative, zero or positive
 */
function compareValues(left, right) {
  if (left === right) {
    return 0;
  }
  if (left === undefined || left === null) {
    return -1;
  }
  if (right === undefined || right === null) {
    return 1;
  }
  if (typeof left === "number" && typeof right === "number") {
    return left - right;
  }
  return String(left).localeCompare(String(right));
}

/**
 * Sort items by the sort keys of a collection query.
 *
 * @param {object[]} items - Items to sort (not mutated)
 * @param {Array<{field: string, descending: boolean}>} sort - Sort keys
 * @returns {object[]} Sorted copy
 */
export function sortItems(items, sort) {
  if (!sort || sort.length === 0) {
    return items.slice();
  }
  return items.slice().sort((left, right) => {
    for (const { field, descending } of sort) {
      const comparison = compareValues(left?.[field], right?.[field]);
      if (comparison !== 0) {
        return descending ? -comparison : comparison;
      }
    }
    return 0;
  });
}

/**
 * Reduce an item to a sparse fieldset.
 *
 * @param {object} item - Item to project
 * @param {string[]|null} fields - Field names, or null for every field
 * @returns {object} Projected item
 */
export function projectFields(item, fields) {
  if (!fields) {
    return item;
  }
  const projected = {};
  for (const field of fields) {
    if (item && Object.hasOwn(item, field)) {
      projected[field] = item[field];
    }
  }
  return projected;
}

/**
 * Run a parsed collection query against an in-memory list.
 *
 * @param {object[]} items - Every item of the collection
 * @param {object} query - Query from {@link parseCollectionQuery}
 * @returns {{items: object[], page: {limit: number, offset: number, total: number, count: number}}} Collection envelope
 */
export function applyCollectionQuery(items, query) {
  const filtered = items.filter((item) => matchesFilters(item, query.filters));
  const sorted = sortItems(filtered, query.sort);
  const page = sorted.slice(query.offset, query.offset + query.limit);
  const projected = page.map((item) => projectFields(item, query.fields));

  return collectionEnvelope(projected, {
    limit: query.limit,
    offset: query.offset,
    total: filtered.length,
  });
}

/**
 * Wrap items in the collection envelope of the specification.
 *
 * @param {object[]} items - Items of this page
 * @param {{limit: number, offset: number, total: number}} page - Page metadata
 * @returns {{items: object[], page: object}} Collection envelope
 */
export function collectionEnvelope(items, page) {
  return {
    items,
    page: {
      limit: page.limit,
      offset: page.offset,
      total: page.total,
      count: items.length,
    },
  };
}

/**
 * Build the RFC 8288 `Link` header value for a paginated collection.
 *
 * @param {string} path - Request path without a query string
 * @param {object} query - Original query parameters
 * @param {{limit: number, offset: number, total: number}} page - Page metadata
 * @returns {string} `Link` header value ("" when there is nothing to link to)
 */
export function paginationLinkHeader(path, query, page) {
  const { limit, offset, total } = page;
  if (!limit) {
    return "";
  }

  const build = (targetOffset) => {
    const parameters = new URLSearchParams();
    for (const [name, value] of Object.entries(query ?? {})) {
      if (name === "limit" || name === "offset") {
        continue;
      }
      for (const item of Array.isArray(value) ? value : [value]) {
        parameters.append(name, String(item));
      }
    }
    parameters.set("limit", String(limit));
    parameters.set("offset", String(targetOffset));
    return `${path}?${parameters.toString()}`;
  };

  const lastOffset = total === 0 ? 0 : Math.floor((total - 1) / limit) * limit;
  const links = [];

  links.push(`<${build(0)}>; rel="first"`);
  if (offset > 0) {
    links.push(`<${build(Math.max(0, offset - limit))}>; rel="prev"`);
  }
  if (offset + limit < total) {
    links.push(`<${build(offset + limit)}>; rel="next"`);
  }
  links.push(`<${build(lastOffset)}>; rel="last"`);

  return links.join(", ");
}
