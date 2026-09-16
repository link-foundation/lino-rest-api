//! Cross-language parity of the codec, ported from
//! `python/tests/test_codec_parity.py`.
//!
//! The crate depends on the published `lino-objects-codec`, and the JavaScript
//! and Python packages depend on the npm package and on a vendored copy of it.
//! These tests run the shared conformance fixtures published by that project,
//! which every implementation must encode to the same bytes, so a
//! representation that drifted between the three languages — and with it an
//! entity tag that no longer matched — would fail here first.
//!
//! The fixtures are written by `node scripts/sync-vendored-codec.mjs`, which
//! copies the same document into `python/tests/fixtures` and into
//! `rust/tests/fixtures`, so each package carries the copy its own suite reads.
//!
//! Rust reports one test per form rather than one per case, because the fixture
//! is read at run time and there is no attribute that can name a case that does
//! not exist until then; every case is still checked, and a failure names the
//! ones that did not match.

use lino_objects_codec::LinoValue;
use lino_rest_api::codec::{decode, decode_single_line, encode, encode_single_line};
use serde_json::Value as Json;

/// The shared fixture document, compiled into the test binary.
const FIXTURES: &str = include_str!("fixtures/readable-format-cases.json");

/// The language id a case names when this implementation has to skip it.
const LANGUAGE: &str = "rust";

/// One fixture case.
struct Case {
    name: String,
    value: LinoValue,
    text: String,
    line: String,
}

/// Turn one fixture value into the value it denotes.
fn materialise(encoded: &Json) -> LinoValue {
    let object = encoded.as_object().expect("a fixture value is an object");
    let (kind, payload) = object
        .iter()
        .next()
        .expect("a fixture value names its type");
    match kind.as_str() {
        "null" => LinoValue::Null,
        "bool" => LinoValue::Bool(payload.as_bool().expect("a boolean payload")),
        "int" => LinoValue::Int(payload.as_i64().expect("an integer payload")),
        "str" => LinoValue::String(payload.as_str().expect("a string payload").to_string()),
        "float" => LinoValue::Float(match payload {
            // The three values JSON cannot spell are named instead.
            Json::String(name) => match name.as_str() {
                "NaN" => f64::NAN,
                "Infinity" => f64::INFINITY,
                "-Infinity" => f64::NEG_INFINITY,
                other => panic!("Unknown float name in a fixture: {other}"),
            },
            other => other.as_f64().expect("a numeric payload"),
        }),
        "array" => LinoValue::Array(
            payload
                .as_array()
                .expect("an array payload")
                .iter()
                .map(materialise)
                .collect(),
        ),
        "object" => LinoValue::Object(
            payload
                .as_array()
                .expect("an object payload is a list of pairs")
                .iter()
                .map(|pair| {
                    let pair = pair.as_array().expect("a pair");
                    let key = pair[0].as_str().expect("a textual key").to_string();
                    (key, materialise(&pair[1]))
                })
                .collect(),
        ),
        other => panic!("Unknown fixture value kind: {other}"),
    }
}

/// Compare two values, treating `NaN` as equal to itself.
///
/// `LinoValue` derives its equality from `f64`, where `NaN != NaN`, so the
/// round trip of the `float_nan` case needs a comparison of its own.
fn equal(left: &LinoValue, right: &LinoValue) -> bool {
    match (left, right) {
        (LinoValue::Float(left), LinoValue::Float(right)) => {
            left == right || (left.is_nan() && right.is_nan())
        }
        (LinoValue::Array(left), LinoValue::Array(right)) => {
            left.len() == right.len() && left.iter().zip(right).all(|(l, r)| equal(l, r))
        }
        (LinoValue::Object(left), LinoValue::Object(right)) => {
            left.len() == right.len()
                && left
                    .iter()
                    .zip(right)
                    .all(|((lk, lv), (rk, rv))| lk == rk && equal(lv, rv))
        }
        (left, right) => left == right,
    }
}

/// The fixture cases this implementation has to satisfy.
fn cases() -> Vec<Case> {
    let document: Json = serde_json::from_str(FIXTURES).expect("the fixtures are well-formed JSON");
    document["cases"]
        .as_array()
        .expect("the fixtures carry a list of cases")
        .iter()
        .filter(|case| case["skip"].get(LANGUAGE).is_none())
        .map(|case| Case {
            name: case["name"].as_str().expect("a named case").to_string(),
            value: materialise(&case["value"]),
            text: case["text"].as_str().expect("an indented form").to_string(),
            line: case["line"]
                .as_str()
                .expect("a single line form")
                .to_string(),
        })
        .collect()
}

/// Report the cases a check did not hold for.
fn report(failures: Vec<String>) {
    assert!(
        failures.is_empty(),
        "{} case(s) did not match:\n{}",
        failures.len(),
        failures.join("\n")
    );
}

#[test]
fn the_fixtures_are_the_ones_the_other_packages_run() {
    let cases = cases();
    // The document published upstream carries every case; a truncated copy
    // would let a real difference pass unnoticed.
    assert!(cases.len() >= 50, "only {} cases were loaded", cases.len());
    assert!(cases.iter().any(|case| case.name == "null_scalar"));
    assert!(
        cases
            .iter()
            .any(|case| case.name == "deeply_nested_objects")
    );
}

#[test]
fn indented_encoding_is_byte_identical_across_languages() {
    let failures = cases()
        .into_iter()
        .filter_map(|case| {
            let encoded = encode(&case.value);
            (encoded != case.text).then(|| {
                format!(
                    "{}: encoded {encoded:?}, expected {:?}",
                    case.name, case.text
                )
            })
        })
        .collect();
    report(failures);
}

#[test]
fn single_line_encoding_is_byte_identical_across_languages() {
    let failures = cases()
        .into_iter()
        .filter_map(|case| {
            let encoded = encode_single_line(&case.value);
            (encoded != case.line).then(|| {
                format!(
                    "{}: encoded {encoded:?}, expected {:?}",
                    case.name, case.line
                )
            })
        })
        .collect();
    report(failures);
}

#[test]
fn both_published_forms_round_trip() {
    let mut failures = Vec::new();
    for case in cases() {
        match decode(&case.text) {
            Ok(decoded) if equal(&decoded, &case.value) => {}
            Ok(decoded) => failures.push(format!(
                "{}: the indented form decoded to {decoded:?}, expected {:?}",
                case.name, case.value
            )),
            Err(error) => failures.push(format!(
                "{}: the indented form did not decode: {error}",
                case.name
            )),
        }
        match decode_single_line(&case.line) {
            Ok(decoded) if equal(&decoded, &case.value) => {}
            Ok(decoded) => failures.push(format!(
                "{}: the single line form decoded to {decoded:?}, expected {:?}",
                case.name, case.value
            )),
            Err(error) => failures.push(format!(
                "{}: the single line form did not decode: {error}",
                case.name
            )),
        }
    }
    report(failures);
}
