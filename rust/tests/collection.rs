//! Tests for collection processing (specification section 6), ported from
//! `python/tests/test_collection.py`.

use lino_objects_codec::LinoValue;
use lino_rest_api::collection::{
    apply_collection_query, collection_envelope, matches_filters, pagination_link_header,
    project_fields, sort_items,
};
use lino_rest_api::query::{
    DEFAULT_LIMIT, Filter, MAX_LIMIT, QueryParams, SortKey, parse_collection_query,
};
use lino_rest_api::value::{array, boolean, get, int, object, string};

/// The three items every test below queries.
fn items() -> Vec<LinoValue> {
    vec![
        object([
            ("id", int(1)),
            ("name", string("charlie")),
            ("done", boolean(false)),
            ("score", int(3)),
        ]),
        object([
            ("id", int(2)),
            ("name", string("alice")),
            ("done", boolean(true)),
            ("score", int(1)),
        ]),
        object([
            ("id", int(3)),
            ("name", string("bob")),
            ("done", boolean(false)),
            ("score", int(2)),
        ]),
    ]
}

/// One filter on one field.
fn filter(field: &str, values: [LinoValue; 1]) -> Filter {
    Filter {
        field: field.to_string(),
        values: values.to_vec(),
    }
}

#[test]
fn filters_compare_equal_values() {
    let first = &items()[0];
    assert!(matches_filters(first, &[filter("done", [boolean(false)])]));
    assert!(!matches_filters(first, &[filter("done", [boolean(true)])]));
}

#[test]
fn a_list_filter_behaves_like_an_any_of_match() {
    let first = &items()[0];
    let any_of = |values: Vec<LinoValue>| {
        vec![Filter {
            field: "name".to_string(),
            values,
        }]
    };
    assert!(matches_filters(
        first,
        &any_of(vec![string("alice"), string("charlie")])
    ));
    assert!(!matches_filters(
        first,
        &any_of(vec![string("alice"), string("bob")])
    ));
}

#[test]
fn sorting_supports_several_keys_and_directions() {
    let ordered = sort_items(
        &items(),
        &[
            SortKey {
                field: "done".to_string(),
                descending: false,
            },
            SortKey {
                field: "name".to_string(),
                descending: true,
            },
        ],
    );
    let identifiers: Vec<&LinoValue> = ordered
        .iter()
        .map(|item| get(item, "id").unwrap())
        .collect();
    assert_eq!(identifiers, vec![&int(1), &int(3), &int(2)]);
}

#[test]
fn sparse_fieldsets_keep_only_the_requested_members() {
    let first = &items()[0];
    let fields = vec!["id".to_string(), "name".to_string()];
    assert_eq!(
        project_fields(first, Some(&fields)),
        object([("id", int(1)), ("name", string("charlie"))])
    );
    assert_eq!(project_fields(first, None), *first);
}

#[test]
fn the_envelope_reports_the_page_and_the_total() {
    let envelope = collection_envelope(vec![items()[0].clone()], 1, 2, 3);
    assert_eq!(
        get(&envelope, "page"),
        Some(&object([
            ("limit", int(1)),
            ("offset", int(2)),
            ("total", int(3)),
            ("count", int(1)),
        ]))
    );
}

#[test]
fn a_query_filters_sorts_paginates_and_projects() {
    let query = QueryParams::parse("done=false&sort=name&limit=1&fields=name");
    let envelope = apply_collection_query(
        &items(),
        &parse_collection_query(&query, DEFAULT_LIMIT, MAX_LIMIT).unwrap(),
    );
    assert_eq!(
        get(&envelope, "items"),
        Some(&array([object([("name", string("bob"))])]))
    );
    assert_eq!(
        get(&envelope, "page"),
        Some(&object([
            ("limit", int(1)),
            ("offset", int(0)),
            ("total", int(2)),
            ("count", int(1)),
        ]))
    );
}

#[test]
fn link_carries_first_prev_next_and_last() {
    let header = pagination_link_header("/items", &QueryParams::parse("done=false"), 10, 10, 35);
    assert!(header.contains(r#"rel="first""#));
    assert!(header.contains("offset=0"));
    assert!(header.contains(r#"rel="prev""#));
    assert!(header.contains(r#"rel="next""#));
    assert!(header.contains("offset=30"));
    assert!(header.contains("done=false"));
}

#[test]
fn the_first_page_has_no_prev_link() {
    let header = pagination_link_header("/items", &QueryParams::new(), 10, 0, 5);
    assert!(!header.contains(r#"rel="prev""#));
    assert!(!header.contains(r#"rel="next""#));
}
