//! Tests for the codec layer (specification sections 2 and 3), ported from
//! `python/tests/test_codec.py`.

use lino_objects_codec::LinoValue;
use lino_rest_api::codec::{
    decode, decode_from, decode_single_line, encode, encode_compact_notation, encode_for,
    encode_single_line, to_json_pretty,
};
use lino_rest_api::media_type::{
    JSON_CONTENT_TYPE, LINO_COMPACT_CONTENT_TYPE, LINO_CONTENT_TYPE, LINO_LINE_CONTENT_TYPE,
    LINO_PROBLEM_CONTENT_TYPE,
};
use lino_rest_api::value::{array, boolean, int, object, string};

#[test]
fn encode_produces_readable_indented_links_notation() {
    let value = object([("name", string("Alice")), ("age", int(30))]);
    assert_eq!(encode(&value), "(\n  name \"Alice\"\n  age 30\n)");
}

#[test]
fn encode_renders_nested_structures_with_indentation() {
    let value = object([(
        "user",
        object([("tags", array([string("a"), string("b")]))]),
    )]);
    assert_eq!(
        encode(&value),
        "(\n  user (\n    tags (\n      \"a\"\n      \"b\"\n    )\n  )\n)"
    );
}

#[test]
fn decode_is_the_inverse_of_encode() {
    let value = object([
        ("name", string("Alice")),
        ("age", int(30)),
        ("active", boolean(true)),
        ("missing", LinoValue::Null),
        ("tags", array([string("developer"), string("rust")])),
        (
            "nested",
            object([("deep", object([("value", LinoValue::Float(1.5))]))]),
        ),
    ]);
    assert_eq!(decode(&encode(&value)).unwrap(), value);
}

#[test]
fn scalars_round_trip() {
    let scalars = [
        int(0),
        int(1),
        int(-1),
        LinoValue::Float(1.5),
        string(""),
        string("text"),
        boolean(true),
        boolean(false),
        LinoValue::Null,
    ];
    for value in scalars {
        assert_eq!(decode(&encode(&value)).unwrap(), value, "{value:?}");
    }
}

#[test]
fn encode_single_line_keeps_the_document_on_one_line() {
    let value = object([("a", int(1)), ("b", array([int(2), int(3)]))]);
    let line = encode_single_line(&value);
    assert!(!line.contains('\n'));
    assert_eq!(decode_single_line(&line).unwrap(), value);
}

#[test]
fn the_compact_representation_preserves_shared_references() {
    let shared = object([("id", int(1))]);
    let compact = encode_compact_notation(&object([
        ("left", shared.clone()),
        ("right", shared.clone()),
    ]));
    let decoded = decode(&compact).unwrap();
    assert_eq!(
        lino_rest_api::value::get(&decoded, "left"),
        lino_rest_api::value::get(&decoded, "right")
    );
    assert_eq!(lino_rest_api::value::get(&decoded, "left"), Some(&shared));
}

#[test]
fn encode_for_dispatches_on_the_media_type() {
    let value = object([("a", int(1))]);
    assert_eq!(
        encode_for(&value, LINO_CONTENT_TYPE).unwrap(),
        encode(&value)
    );
    assert_eq!(
        encode_for(&value, LINO_LINE_CONTENT_TYPE).unwrap(),
        encode_single_line(&value)
    );
    assert_eq!(
        encode_for(&value, LINO_COMPACT_CONTENT_TYPE).unwrap(),
        encode_compact_notation(&value)
    );
    assert_eq!(encode_for(&value, JSON_CONTENT_TYPE).unwrap(), r#"{"a":1}"#);
}

#[test]
fn decode_from_dispatches_on_the_media_type() {
    let value = object([("a", int(1))]);
    assert_eq!(
        decode_from("(\n  a 1\n)", LINO_CONTENT_TYPE).unwrap(),
        value
    );
    assert_eq!(
        decode_from("(o: (a 1))", LINO_LINE_CONTENT_TYPE).unwrap(),
        value
    );
    assert_eq!(decode_from(r#"{"a":1}"#, JSON_CONTENT_TYPE).unwrap(), value);
}

#[test]
fn problem_media_types_decode_as_their_base_representation() {
    assert_eq!(
        decode_from("(\n  status 404\n)", LINO_PROBLEM_CONTENT_TYPE).unwrap(),
        object([("status", int(404))])
    );
}

#[test]
fn encode_for_rejects_an_unknown_media_type() {
    let error = encode_for(&object([("a", int(1))]), "image/png").unwrap_err();
    assert_eq!(error.to_string(), "Unsupported media type: image/png");
}

#[test]
fn json_is_written_the_way_json_stringify_writes_it() {
    // The OpenAPI document is served as `JSON.stringify(document, null, 2)`, so
    // the three implementations publish the same bytes and the same entity tag.
    let value = object([
        ("list", array([int(1), int(2)])),
        ("empty", array([])),
        ("nested", object([("deep", string("value"))])),
    ]);
    assert_eq!(
        to_json_pretty(&value),
        "{\n  \"list\": [\n    1,\n    2\n  ],\n  \"empty\": [],\n  \"nested\": {\n    \"deep\": \"value\"\n  }\n}"
    );
}
