/**
 * In-memory resource store.
 *
 * Implements the store interface {@link LinoApp#resource} expects, so that a
 * working CRUD API is one call away in examples, tests and prototypes.
 */

import { applyCollectionQuery } from "./collection.js";

/**
 * A resource store backed by a `Map`.
 */
export class MemoryStore {
  /**
   * @param {object} [options] - Store options
   * @param {string} [options.idField] - Name of the identifier field
   * @param {object[]} [options.items] - Items to seed the store with
   */
  constructor(options = {}) {
    this.idField = options.idField ?? "id";
    this.items = new Map();
    this.nextId = 1;
    for (const item of options.items ?? []) {
      this.create(item);
    }
  }

  /**
   * Normalise an identifier so that `"1"` from a path matches the stored `1`.
   *
   * @param {*} id - Raw identifier
   * @returns {*} Normalised identifier
   */
  normalizeId(id) {
    if (typeof id === "string" && id !== "" && !Number.isNaN(Number(id))) {
      return Number(id);
    }
    return id;
  }

  /**
   * Run a collection query against the store.
   *
   * @param {object} query - Query from `parseCollectionQuery`
   * @returns {{items: object[], page: object}} Collection envelope
   */
  list(query) {
    return applyCollectionQuery([...this.items.values()], query);
  }

  /**
   * Read one item.
   *
   * @param {*} id - Identifier
   * @returns {object|undefined} Item, or undefined when absent
   */
  get(id) {
    return this.items.get(this.normalizeId(id));
  }

  /**
   * Create an item, assigning an identifier when the body does not carry one.
   *
   * @param {object} body - Item body
   * @returns {object} Created item
   */
  create(body) {
    const provided = body?.[this.idField];
    const id =
      provided === undefined ? this.nextId++ : this.normalizeId(provided);
    if (typeof id === "number" && id >= this.nextId) {
      this.nextId = id + 1;
    }
    const item = { ...body, [this.idField]: id };
    this.items.set(id, item);
    return item;
  }

  /**
   * Replace an item.
   *
   * @param {*} id - Identifier
   * @param {object} body - Replacement body
   * @returns {object|undefined} Updated item, or undefined when absent
   */
  update(id, body) {
    const key = this.normalizeId(id);
    if (!this.items.has(key)) {
      return undefined;
    }
    const item = { ...body, [this.idField]: key };
    this.items.set(key, item);
    return item;
  }

  /**
   * Merge changes into an item.
   *
   * @param {*} id - Identifier
   * @param {object} body - Partial body
   * @returns {object|undefined} Updated item, or undefined when absent
   */
  patch(id, body) {
    const key = this.normalizeId(id);
    const existing = this.items.get(key);
    if (!existing) {
      return undefined;
    }
    const item = { ...existing, ...body, [this.idField]: key };
    this.items.set(key, item);
    return item;
  }

  /**
   * Delete an item.
   *
   * @param {*} id - Identifier
   * @returns {boolean} True when an item was deleted
   */
  remove(id) {
    return this.items.delete(this.normalizeId(id));
  }

  /**
   * Remove every item.
   *
   * @returns {void}
   */
  clear() {
    this.items.clear();
    this.nextId = 1;
  }
}
