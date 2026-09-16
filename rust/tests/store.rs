//! The in-memory store, ported from `python/tests/test_store.py`.

use lino_objects_codec::LinoValue;
use lino_rest_api::query::{DEFAULT_LIMIT, MAX_LIMIT, QueryParams, parse_collection_query};
use lino_rest_api::store::{MemoryStore, Store, id_to_string, normalize_id};
use lino_rest_api::value::{as_array, get, int, object, string};

/// The member of a value, which every test below expects to be there.
fn member<'a>(value: &'a LinoValue, key: &str) -> &'a LinoValue {
    get(value, key).unwrap_or_else(|| panic!("value has no member {key}"))
}

/// An item with a name, as the Python tests seed them.
fn named(name: &str) -> LinoValue {
    object([("name", string(name))])
}

#[test]
fn seeded_items_receive_sequential_identifiers() {
    let store = MemoryStore::seeded([named("a"), named("b")]);
    assert_eq!(
        store.read("1"),
        Some(object([("name", string("a")), ("id", int(1))]))
    );
    assert_eq!(
        store.read("2"),
        Some(object([("name", string("b")), ("id", int(2))]))
    );
}

#[test]
fn an_identifier_from_a_path_is_normalised() {
    let store = MemoryStore::seeded([named("a")]);
    assert_eq!(
        store.read("1"),
        Some(object([("name", string("a")), ("id", int(1))]))
    );
    assert_eq!(normalize_id("abc"), string("abc"));
    assert_eq!(normalize_id("1"), int(1));
    assert_eq!(id_to_string(&int(1)), "1");
}

#[tokio::test]
async fn a_provided_identifier_is_honoured_and_moves_the_counter() {
    let store = MemoryStore::new();
    store
        .create(&object([("id", int(10)), ("name", string("ten"))]))
        .await
        .expect("the item is created");
    let next = store
        .create(&named("next"))
        .await
        .expect("the item is created");
    assert_eq!(member(&next, "id"), &int(11));
}

#[tokio::test]
async fn update_replaces_and_patch_merges() {
    let store = MemoryStore::seeded([object([
        ("name", string("a")),
        ("done", LinoValue::Bool(false)),
    ])]);
    assert_eq!(
        store
            .update("1", &named("b"))
            .await
            .expect("the update succeeds"),
        Some(object([("name", string("b")), ("id", int(1))]))
    );
    assert_eq!(
        store
            .patch("1", &object([("done", LinoValue::Bool(true))]))
            .await
            .expect("the patch succeeds"),
        Some(object([
            ("name", string("b")),
            ("id", int(1)),
            ("done", LinoValue::Bool(true)),
        ]))
    );
    assert_eq!(
        store
            .update("99", &LinoValue::Object(Vec::new()))
            .await
            .expect("the update succeeds"),
        None
    );
    assert_eq!(
        store
            .patch("99", &LinoValue::Object(Vec::new()))
            .await
            .expect("the patch succeeds"),
        None
    );
}

#[tokio::test]
async fn remove_reports_whether_anything_was_deleted() {
    let store = MemoryStore::seeded([named("a")]);
    assert!(store.remove("1").await.expect("the removal succeeds"));
    assert!(!store.remove("1").await.expect("the removal succeeds"));
}

#[tokio::test]
async fn list_applies_a_collection_query() {
    let store = MemoryStore::seeded([
        object([("name", string("a")), ("done", LinoValue::Bool(true))]),
        object([("name", string("b")), ("done", LinoValue::Bool(false))]),
    ]);
    let query = parse_collection_query(&QueryParams::parse("done=true"), DEFAULT_LIMIT, MAX_LIMIT)
        .expect("the query parses");
    let envelope = store.list(&query).await.expect("the listing succeeds");
    assert_eq!(member(member(&envelope, "page"), "total"), &int(1));
    let items = as_array(member(&envelope, "items")).expect("items is an array");
    assert_eq!(member(&items[0], "name"), &string("a"));
}

#[tokio::test]
async fn clear_empties_the_store() {
    let store = MemoryStore::seeded([named("a")]);
    store.clear();
    assert!(store.is_empty());
    assert_eq!(store.items(), Vec::new());
    let created = store
        .create(&named("b"))
        .await
        .expect("the item is created");
    assert_eq!(member(&created, "id"), &int(1));
}

#[tokio::test]
async fn a_custom_identifier_field_is_supported() {
    let store = MemoryStore::with_id_field("key");
    assert_eq!(store.id_field(), "key");
    let created = store
        .create(&named("a"))
        .await
        .expect("the item is created");
    assert_eq!(member(&created, "key"), &int(1));
}

#[tokio::test]
async fn creating_an_item_at_an_existing_identifier_replaces_it() {
    let store = MemoryStore::seeded([named("a")]);
    store
        .create(&object([("id", int(1)), ("name", string("replaced"))]))
        .await
        .expect("the item is created");
    assert_eq!(store.len(), 1);
    assert_eq!(
        member(&store.read("1").expect("the item is there"), "name"),
        &string("replaced")
    );
}
