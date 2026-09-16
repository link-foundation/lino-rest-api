//! Helpers for building and reading [`LinoValue`] objects.
//!
//! Links Notation objects keep their keys in insertion order, which is what makes
//! entity tags reproducible across implementations, so every helper here
//! preserves that order.

use lino_objects_codec::LinoValue;

/// Build an object from its members, keeping them in the given order.
///
/// # Examples
///
/// ```
/// use lino_rest_api::value::{object, string};
///
/// let task = object([("title", string("Ship it"))]);
/// assert_eq!(lino_rest_api::codec::encode(&task), "(\n  title \"Ship it\"\n)");
/// ```
pub fn object<I, K>(members: I) -> LinoValue
where
    I: IntoIterator<Item = (K, LinoValue)>,
    K: Into<String>,
{
    LinoValue::Object(
        members
            .into_iter()
            .map(|(key, value)| (key.into(), value))
            .collect(),
    )
}

/// Build an array from its items.
pub fn array<I: IntoIterator<Item = LinoValue>>(items: I) -> LinoValue {
    LinoValue::Array(items.into_iter().collect())
}

/// A string value.
pub fn string<S: Into<String>>(text: S) -> LinoValue {
    LinoValue::String(text.into())
}

/// An integer value.
pub fn int(number: i64) -> LinoValue {
    LinoValue::Int(number)
}

/// A boolean value.
pub fn boolean(flag: bool) -> LinoValue {
    LinoValue::Bool(flag)
}

/// The members of a value when it is an object.
pub fn as_object(value: &LinoValue) -> Option<&Vec<(String, LinoValue)>> {
    match value {
        LinoValue::Object(members) => Some(members),
        _ => None,
    }
}

/// The items of a value when it is an array.
pub fn as_array(value: &LinoValue) -> Option<&Vec<LinoValue>> {
    match value {
        LinoValue::Array(items) => Some(items),
        _ => None,
    }
}

/// The text of a value when it is a string.
pub fn as_str(value: &LinoValue) -> Option<&str> {
    match value {
        LinoValue::String(text) => Some(text),
        _ => None,
    }
}

/// Read a member of an object, or [`None`] when it is absent or the value is not
/// an object.
pub fn get<'a>(value: &'a LinoValue, key: &str) -> Option<&'a LinoValue> {
    as_object(value)?
        .iter()
        .find(|(name, _)| name == key)
        .map(|(_, member)| member)
}

/// Whether an object carries a member.
pub fn has(value: &LinoValue, key: &str) -> bool {
    get(value, key).is_some()
}

/// Set a member, replacing it in place when it is already present so that the
/// order of the other members is untouched.
pub fn set<S: Into<String>>(value: &mut LinoValue, key: S, member: LinoValue) {
    let key = key.into();
    if let LinoValue::Object(members) = value {
        if let Some(existing) = members.iter_mut().find(|(name, _)| *name == key) {
            existing.1 = member;
        } else {
            members.push((key, member));
        }
    }
}

/// An object with one member replaced or appended, leaving the original untouched.
pub fn with<S: Into<String>>(value: &LinoValue, key: S, member: LinoValue) -> LinoValue {
    let mut copy = value.clone();
    if !matches!(copy, LinoValue::Object(_)) {
        copy = LinoValue::Object(Vec::new());
    }
    set(&mut copy, key, member);
    copy
}

/// Merge the members of `patch` into `base`, as `PATCH` does.
pub fn merge(base: &LinoValue, patch: &LinoValue) -> LinoValue {
    let mut merged = base.clone();
    if !matches!(merged, LinoValue::Object(_)) {
        merged = LinoValue::Object(Vec::new());
    }
    if let Some(members) = as_object(patch) {
        for (key, member) in members {
            set(&mut merged, key.clone(), member.clone());
        }
    }
    merged
}

/// Render a value the way a query string or a path segment spells it.
///
/// Booleans are `true`/`false` and whole floats lose their fraction, so that the
/// Rust client sends exactly what the Python and JavaScript clients send.
pub fn to_query_text(value: &LinoValue) -> String {
    match value {
        LinoValue::Null => "null".to_string(),
        LinoValue::Bool(flag) => flag.to_string(),
        LinoValue::Int(number) => number.to_string(),
        LinoValue::Float(number) => format_float(*number),
        LinoValue::String(text) => text.clone(),
        other => crate::codec::encode_single_line(other),
    }
}

/// Format a float the way JSON does: whole numbers keep no fraction.
pub fn format_float(number: f64) -> String {
    if number.is_finite() && number.fract() == 0.0 && number.abs() < 1e15 {
        format!("{}", number as i64)
    } else {
        format!("{number}")
    }
}

/// Compare two values in a total order that works across every scalar type.
///
/// Absent values sort first, numbers sort numerically among themselves, and
/// everything else sorts as the text of [`to_query_text`], which is the order
/// the JavaScript and Python packages produce.
pub fn compare(left: &LinoValue, right: &LinoValue) -> std::cmp::Ordering {
    use std::cmp::Ordering;
    match (left, right) {
        (LinoValue::Null, LinoValue::Null) => Ordering::Equal,
        (LinoValue::Null, _) => Ordering::Less,
        (_, LinoValue::Null) => Ordering::Greater,
        (LinoValue::Int(a), LinoValue::Int(b)) => a.cmp(b),
        (LinoValue::Int(a), LinoValue::Float(b)) => {
            (*a as f64).partial_cmp(b).unwrap_or(Ordering::Equal)
        }
        (LinoValue::Float(a), LinoValue::Int(b)) => {
            a.partial_cmp(&(*b as f64)).unwrap_or(Ordering::Equal)
        }
        (LinoValue::Float(a), LinoValue::Float(b)) => a.partial_cmp(b).unwrap_or(Ordering::Equal),
        (a, b) => to_query_text(a).cmp(&to_query_text(b)),
    }
}
