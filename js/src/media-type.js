/**
 * Media types and content negotiation (specification §2).
 *
 * Negotiation follows RFC 9110 §12.5.1: the `Accept` header is parsed into ranges
 * with quality values, the ranges are ordered by quality and then by specificity,
 * and the first range that matches a representation the server can produce wins.
 */

/** Readable, indented Links Notation. The default representation. */
export const LINO_CONTENT_TYPE = "text/lino";

/** Readable Links Notation restricted to one line per value. */
export const LINO_LINE_CONTENT_TYPE = "text/lino-line";

/** Type-tagged, base64 Links Notation that preserves object identity. */
export const LINO_COMPACT_CONTENT_TYPE = "text/lino-compact";

/** JSON fallback for clients that cannot speak Links Notation. */
export const JSON_CONTENT_TYPE = "application/json";

/** Problem details served as Links Notation. */
export const LINO_PROBLEM_CONTENT_TYPE = "application/problem+lino";

/** Media type of RFC 9457 problem details expressed as JSON. */
export const JSON_PROBLEM_CONTENT_TYPE = "application/problem+json";

/**
 * Problem-details media type to use for each representation.
 *
 * A `4xx` served as `text/lino` is announced as `application/problem+lino`, which
 * lets a client tell an error body from a successful one without parsing it.
 */
export const PROBLEM_MEDIA_TYPES = {
  [LINO_CONTENT_TYPE]: LINO_PROBLEM_CONTENT_TYPE,
  [JSON_CONTENT_TYPE]: JSON_PROBLEM_CONTENT_TYPE,
};

/** Representation each problem-details media type is encoded as. */
const PROBLEM_BASE_MEDIA_TYPES = {
  [LINO_PROBLEM_CONTENT_TYPE]: LINO_CONTENT_TYPE,
  [JSON_PROBLEM_CONTENT_TYPE]: JSON_CONTENT_TYPE,
};

/**
 * Every representation a server produces, most preferred first.
 *
 * @type {string[]}
 */
export const SUPPORTED_MEDIA_TYPES = [
  LINO_CONTENT_TYPE,
  LINO_LINE_CONTENT_TYPE,
  LINO_COMPACT_CONTENT_TYPE,
  JSON_CONTENT_TYPE,
];

/**
 * Add `charset=utf-8` to a media type so that bytes are unambiguous.
 *
 * @param {string} mediaType - Bare media type
 * @returns {string} Media type with an explicit charset
 */
export function withCharset(mediaType) {
  return `${mediaType}; charset=utf-8`;
}

/**
 * Strip parameters and normalise case, turning a header value into a media type.
 *
 * @param {string} [headerValue] - Raw `Content-Type` header value
 * @returns {string} Bare, lower-cased media type ("" when absent)
 */
export function parseContentType(headerValue) {
  if (!headerValue) {
    return "";
  }
  return headerValue.split(";")[0].trim().toLowerCase();
}

/**
 * Parse an `Accept` header into ranges ordered by preference.
 *
 * @param {string} [headerValue] - Raw `Accept` header value
 * @returns {Array<{type: string, quality: number, specificity: number}>} Ordered ranges
 */
export function parseAccept(headerValue) {
  if (!headerValue || !headerValue.trim()) {
    return [{ type: "*/*", quality: 1, specificity: 0 }];
  }

  const ranges = headerValue
    .split(",")
    .map((part, index) => {
      const [rawType, ...parameters] = part.split(";");
      const type = rawType.trim().toLowerCase();
      if (!type) {
        return null;
      }

      let quality = 1;
      for (const parameter of parameters) {
        const [name, value] = parameter.split("=");
        if (name && name.trim().toLowerCase() === "q") {
          const parsed = Number.parseFloat(value);
          quality = Number.isNaN(parsed) ? 0 : parsed;
        }
      }

      let specificity = 2;
      if (type === "*/*") {
        specificity = 0;
      } else if (type.endsWith("/*")) {
        specificity = 1;
      }

      return { type, quality, specificity, index };
    })
    .filter((range) => range !== null);

  ranges.sort((left, right) => {
    if (right.quality !== left.quality) {
      return right.quality - left.quality;
    }
    if (right.specificity !== left.specificity) {
      return right.specificity - left.specificity;
    }
    return left.index - right.index;
  });

  return ranges.map(({ type, quality, specificity }) => ({
    type,
    quality,
    specificity,
  }));
}

/**
 * Test whether an `Accept` range matches a concrete media type.
 *
 * @param {string} range - Range from an `Accept` header
 * @param {string} mediaType - Concrete media type
 * @returns {boolean} True when the range covers the media type
 */
function rangeMatches(range, mediaType) {
  if (range === "*/*") {
    return true;
  }
  if (range === mediaType) {
    return true;
  }
  if (range.endsWith("/*")) {
    return mediaType.startsWith(`${range.slice(0, -1)}`);
  }
  return false;
}

/**
 * Select the representation to produce for a request.
 *
 * @param {string} [acceptHeader] - Raw `Accept` header value
 * @param {string[]} [supported] - Representations the server can produce
 * @returns {string|null} Selected media type, or null when none is acceptable
 */
export function negotiateMediaType(
  acceptHeader,
  supported = SUPPORTED_MEDIA_TYPES,
) {
  for (const range of parseAccept(acceptHeader)) {
    if (range.quality <= 0) {
      continue;
    }
    const match = supported.find((mediaType) =>
      rangeMatches(range.type, mediaType),
    );
    if (match) {
      return match;
    }
  }
  return null;
}

/**
 * Test whether a request body media type can be decoded.
 *
 * @param {string} mediaType - Bare media type of the request body
 * @returns {boolean} True when the body can be decoded
 */
export function isDecodableMediaType(mediaType) {
  return SUPPORTED_MEDIA_TYPES.includes(normalizeMediaType(mediaType));
}

/**
 * Resolve a media type to the representation it is encoded as.
 *
 * Problem-details types carry the same syntax as their base representation, so
 * they decode with the same codec.
 *
 * @param {string} mediaType - Bare media type
 * @returns {string} Representation media type
 */
export function normalizeMediaType(mediaType) {
  return PROBLEM_BASE_MEDIA_TYPES[mediaType] ?? mediaType;
}

/**
 * Problem-details media type matching a representation.
 *
 * @param {string} mediaType - Representation media type
 * @returns {string} Media type to announce for problem details
 */
export function problemMediaType(mediaType) {
  return PROBLEM_MEDIA_TYPES[mediaType] ?? mediaType;
}
