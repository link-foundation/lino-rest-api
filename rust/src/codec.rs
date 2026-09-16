//! Codec layer: every conversion between a [`LinoValue`] and the wire.
//!
//! All Links Notation work is delegated to [`lino_objects_codec`], which
//! produces byte-identical readable output in JavaScript, Python, Rust and C#;
//! this module adapts it and adds the media-type dispatch described in
//! `docs/spec/README.md` section 2.

use std::fmt;

use lino_objects_codec::{
    LinoValue, decode as decode_any, decode_line, encode as encode_readable, encode_compact,
    encode_line,
};
use serde_json::{Map, Number, Value as JsonValue};

use crate::media_type::{
    JSON_CONTENT_TYPE, LINO_COMPACT_CONTENT_TYPE, LINO_CONTENT_TYPE, LINO_LINE_CONTENT_TYPE,
    normalize_media_type,
};

/// Why a value could not be moved between a representation and a [`LinoValue`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CodecError {
    /// The media type is not a representation of this API.
    UnsupportedMediaType(String),
    /// The body is not a well-formed document of its media type.
    Malformed(String),
}

impl fmt::Display for CodecError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            CodecError::UnsupportedMediaType(media_type) => {
                write!(formatter, "Unsupported media type: {media_type}")
            }
            CodecError::Malformed(detail) => write!(formatter, "{detail}"),
        }
    }
}

impl std::error::Error for CodecError {}

/// Encode a value as readable, indented Links Notation.
pub fn encode(value: &LinoValue) -> String {
    encode_readable(value)
}

/// Decode readable or compact Links Notation into a value.
pub fn decode(notation: &str) -> Result<LinoValue, CodecError> {
    decode_any(notation).map_err(|error| CodecError::Malformed(error.to_string()))
}

/// Encode a value as single-line readable Links Notation.
pub fn encode_single_line(value: &LinoValue) -> String {
    encode_line(value)
}

/// Decode one line of single-line readable Links Notation.
pub fn decode_single_line(notation: &str) -> Result<LinoValue, CodecError> {
    decode_line(notation).map_err(|error| CodecError::Malformed(error.to_string()))
}

/// Encode a value as compact, type-tagged Links Notation.
///
/// This is the only representation that preserves shared object identity and
/// circular references.
pub fn encode_compact_notation(value: &LinoValue) -> String {
    encode_compact(value)
}

/// Encode a value for a concrete media type.
pub fn encode_for(value: &LinoValue, media_type: &str) -> Result<String, CodecError> {
    match normalize_media_type(media_type) {
        LINO_CONTENT_TYPE => Ok(encode(value)),
        LINO_LINE_CONTENT_TYPE => Ok(encode_single_line(value)),
        LINO_COMPACT_CONTENT_TYPE => Ok(encode_compact_notation(value)),
        JSON_CONTENT_TYPE => Ok(to_json_string(value)),
        _ => Err(CodecError::UnsupportedMediaType(media_type.to_string())),
    }
}

/// Decode a representation of a concrete media type.
pub fn decode_from(body: &str, media_type: &str) -> Result<LinoValue, CodecError> {
    match normalize_media_type(media_type) {
        LINO_CONTENT_TYPE | LINO_COMPACT_CONTENT_TYPE => decode(body),
        LINO_LINE_CONTENT_TYPE => decode_single_line(body),
        JSON_CONTENT_TYPE => {
            let json: JsonValue = serde_json::from_str(body)
                .map_err(|error| CodecError::Malformed(error.to_string()))?;
            Ok(from_json(&json))
        }
        _ => Err(CodecError::UnsupportedMediaType(media_type.to_string())),
    }
}

/// Encode a value as JSON.
///
/// The separators and the raw Unicode match `JSON.stringify` byte for byte, so
/// that the entity tag of a representation (section 7) is the same whichever
/// implementation of this specification serves it.
pub fn to_json_string(value: &LinoValue) -> String {
    let mut out = String::new();
    write_json(value, &mut out);
    out
}

/// Append the JSON form of a value to a buffer.
fn write_json(value: &LinoValue, out: &mut String) {
    match value {
        LinoValue::Null => out.push_str("null"),
        LinoValue::Bool(flag) => out.push_str(if *flag { "true" } else { "false" }),
        LinoValue::Int(number) => out.push_str(&number.to_string()),
        // JSON has no NaN or Infinity; JSON.stringify writes them as null.
        LinoValue::Float(number) => {
            if number.is_finite() {
                out.push_str(&JsonValue::from(*number).to_string());
            } else {
                out.push_str("null");
            }
        }
        LinoValue::String(text) => out.push_str(&JsonValue::String(text.clone()).to_string()),
        LinoValue::Array(items) => {
            out.push('[');
            for (index, item) in items.iter().enumerate() {
                if index > 0 {
                    out.push(',');
                }
                write_json(item, out);
            }
            out.push(']');
        }
        // Object keys keep the order they were inserted in, as they do in
        // JavaScript and Python, so the encoded bytes are the same everywhere.
        LinoValue::Object(entries) => {
            out.push('{');
            for (index, (key, item)) in entries.iter().enumerate() {
                if index > 0 {
                    out.push(',');
                }
                out.push_str(&JsonValue::String(key.clone()).to_string());
                out.push(':');
                write_json(item, out);
            }
            out.push('}');
        }
    }
}

/// Convert a [`serde_json::Value`] into a [`LinoValue`], keeping key order.
pub fn from_json(value: &JsonValue) -> LinoValue {
    match value {
        JsonValue::Null => LinoValue::Null,
        JsonValue::Bool(flag) => LinoValue::Bool(*flag),
        JsonValue::Number(number) => match number.as_i64() {
            Some(integer) => LinoValue::Int(integer),
            None => LinoValue::Float(number.as_f64().unwrap_or(f64::NAN)),
        },
        JsonValue::String(text) => LinoValue::String(text.clone()),
        JsonValue::Array(items) => LinoValue::Array(items.iter().map(from_json).collect()),
        JsonValue::Object(entries) => LinoValue::Object(
            entries
                .iter()
                .map(|(key, item)| (key.clone(), from_json(item)))
                .collect(),
        ),
    }
}

/// Convert a [`LinoValue`] into a [`serde_json::Value`], keeping key order.
pub fn to_json(value: &LinoValue) -> JsonValue {
    match value {
        LinoValue::Null => JsonValue::Null,
        LinoValue::Bool(flag) => JsonValue::Bool(*flag),
        LinoValue::Int(number) => JsonValue::Number(Number::from(*number)),
        LinoValue::Float(number) => Number::from_f64(*number)
            .map(JsonValue::Number)
            .unwrap_or(JsonValue::Null),
        LinoValue::String(text) => JsonValue::String(text.clone()),
        LinoValue::Array(items) => JsonValue::Array(items.iter().map(to_json).collect()),
        LinoValue::Object(entries) => {
            let mut map = Map::new();
            for (key, item) in entries {
                map.insert(key.clone(), to_json(item));
            }
            JsonValue::Object(map)
        }
    }
}
