/**
 * Route registry backing automatic `HEAD`, automatic `OPTIONS`, `405 Method Not
 * Allowed` and the service description (specification §4.1 and §9).
 *
 * The registry keeps its own matcher rather than reading Express internals, so it
 * stays valid across Express versions.
 */

/** Methods that never need to be registered explicitly. */
export const IMPLICIT_METHODS = ["HEAD", "OPTIONS"];

/**
 * Compile an Express-style path pattern into a matcher.
 *
 * Supports `:param` segments and a trailing `*` wildcard, which is the subset the
 * registry needs in order to answer "does any route own this path?".
 *
 * @param {string} pattern - Path pattern
 * @returns {RegExp} Matcher anchored to the whole path
 */
export function compilePathPattern(pattern) {
  const source = pattern
    .split("/")
    .map((segment) => {
      if (segment.startsWith(":")) {
        return "[^/]+";
      }
      if (segment === "*" || segment.startsWith("*")) {
        return ".*";
      }
      return segment.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    })
    .join("/");
  return new RegExp(`^${source}/?$`);
}

/**
 * The set of routes registered on an application.
 */
export class RouteTable {
  constructor() {
    /** @type {Map<string, {pattern: string, matcher: RegExp, methods: Map<string, object>}>} */
    this.routes = new Map();
  }

  /**
   * Register a method on a path.
   *
   * @param {string} method - HTTP method
   * @param {string} pattern - Path pattern
   * @param {object} [meta] - Description metadata for §9
   * @returns {void}
   */
  register(method, pattern, meta = {}) {
    let entry = this.routes.get(pattern);
    if (!entry) {
      entry = {
        pattern,
        matcher: compilePathPattern(pattern),
        methods: new Map(),
      };
      this.routes.set(pattern, entry);
    }
    entry.methods.set(method.toUpperCase(), meta);
  }

  /**
   * Find the route entry owning a concrete path.
   *
   * @param {string} pathname - Request path
   * @returns {object|undefined} Route entry, or undefined when unowned
   */
  find(pathname) {
    for (const entry of this.routes.values()) {
      if (entry.matcher.test(pathname)) {
        return entry;
      }
    }
    return undefined;
  }

  /**
   * List the methods allowed on a concrete path.
   *
   * `OPTIONS` is always allowed, and `HEAD` is allowed wherever `GET` is.
   *
   * @param {string} pathname - Request path
   * @returns {string[]|null} Allowed methods, or null when the path is unowned
   */
  allowedMethods(pathname) {
    const entry = this.find(pathname);
    if (!entry) {
      return null;
    }
    const methods = new Set(entry.methods.keys());
    if (methods.has("GET")) {
      methods.add("HEAD");
    }
    methods.add("OPTIONS");
    return [...methods].sort();
  }

  /**
   * Render the registry as the `routes` member of a service description.
   *
   * @returns {Array<{path: string, methods: string[], summary: string}>} Route descriptions
   */
  describe() {
    return [...this.routes.values()]
      .map((entry) => {
        const methods = this.allowedMethods(entry.pattern) ?? [];
        const summary = [...entry.methods.values()].find(
          (meta) => meta?.summary,
        )?.summary;
        const description = { path: entry.pattern, methods };
        if (summary) {
          description.summary = summary;
        }
        return description;
      })
      .sort((left, right) => left.path.localeCompare(right.path));
  }
}
