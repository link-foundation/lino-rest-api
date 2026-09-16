//! Collection query parsing, ported from `python/tests/test_query.py`
//! (specification section 6).

use lino_objects_codec::LinoValue;
use lino_rest_api::query::{
    DEFAULT_LIMIT, Filter, MAX_LIMIT, QueryParams, SortKey, parse_collection_query, parse_fields,
    parse_scalar, parse_sort,
};
use lino_rest_api::value::{int, string};

/// Parse a query string with the default page size bounds.
fn parse(query_string: &str) -> lino_rest_api::query::CollectionQuery {
    parse_collection_query(&QueryParams::parse(query_string), DEFAULT_LIMIT, MAX_LIMIT)
        .expect("query parses")
}

/// A sort key, spelled the way the tests read it.
fn key(field: &str, descending: bool) -> SortKey {
    SortKey {
        field: field.to_string(),
        descending,
    }
}

#[test]
fn scalars_in_the_query_string_are_typed() {
    assert_eq!(parse_scalar("42"), int(42));
    assert_eq!(parse_scalar("1.5"), LinoValue::Float(1.5));
    assert_eq!(parse_scalar("true"), LinoValue::Bool(true));
    assert_eq!(parse_scalar("false"), LinoValue::Bool(false));
    assert_eq!(parse_scalar("null"), LinoValue::Null);
    assert_eq!(parse_scalar("text"), string("text"));
    assert_eq!(parse_scalar(""), string(""));
}

#[test]
fn sort_accepts_a_comma_separated_list_with_descending_prefixes() {
    assert_eq!(
        parse_sort(Some("-created,name")),
        vec![key("created", true), key("name", false)]
    );
    assert_eq!(parse_sort(None), Vec::new());
}

#[test]
fn fields_is_none_when_absent_and_a_list_when_present() {
    assert_eq!(parse_fields(None), None);
    assert_eq!(
        parse_fields(Some("id,name")),
        Some(vec!["id".to_string(), "name".to_string()])
    );
}

#[test]
fn defaults_apply_when_the_query_is_empty() {
    let query = parse("");
    assert_eq!(query.limit, DEFAULT_LIMIT);
    assert_eq!(query.offset, 0);
    assert_eq!(query.sort, Vec::new());
    assert_eq!(query.fields, None);
    assert_eq!(query.filters, Vec::new());
}

#[test]
fn non_reserved_parameters_become_filters() {
    let query = parse("limit=5&offset=10&sort=-name&fields=id&done=true&tag=a&tag=b");
    assert_eq!(query.limit, 5);
    assert_eq!(query.offset, 10);
    assert_eq!(
        query.filters,
        vec![
            Filter {
                field: "done".to_string(),
                values: vec![LinoValue::Bool(true)],
            },
            Filter {
                field: "tag".to_string(),
                values: vec![string("a"), string("b")],
            },
        ]
    );
}

#[test]
fn limit_is_clamped_to_the_maximum() {
    assert_eq!(parse(&format!("limit={}", MAX_LIMIT + 50)).limit, MAX_LIMIT);
}

#[test]
fn a_malformed_limit_is_a_400() {
    let bad_limit =
        parse_collection_query(&QueryParams::parse("limit=abc"), DEFAULT_LIMIT, MAX_LIMIT)
            .expect_err("a malformed limit is refused");
    assert_eq!(bad_limit.status, 400);

    let bad_offset =
        parse_collection_query(&QueryParams::parse("offset=-1"), DEFAULT_LIMIT, MAX_LIMIT)
            .expect_err("a negative offset is refused");
    assert_eq!(bad_offset.status, 400);
}

#[test]
fn the_page_size_bounds_can_be_overridden() {
    let query =
        parse_collection_query(&QueryParams::parse("limit=500"), 5, 200).expect("query parses");
    assert_eq!(query.limit, 200);
    assert_eq!(
        parse_collection_query(&QueryParams::new(), 5, MAX_LIMIT)
            .expect("query parses")
            .limit,
        5
    );
}

#[test]
fn query_parameters_are_form_decoded_and_round_trip() {
    let query = QueryParams::parse("?name=a+b&tag=%C3%A9");
    assert_eq!(query.get_last("name"), Some("a b"));
    assert_eq!(query.get_last("tag"), Some("é"));
    assert_eq!(query.to_query_string(), "name=a+b&tag=%C3%A9");
}
