//! Collection query parsing (specification sections 6.2 - 6.4).
//!
//! Turns the reserved query parameters (`limit`, `offset`, `sort`, `fields`) and
//! the free-form field filters of a request URL into a structured query.

use lino_objects_codec::LinoValue;

use crate::problem::LinoHttpError;

/// Query parameters that are not field filters.
pub const RESERVED_QUERY_PARAMETERS: [&str; 4] = ["limit", "offset", "sort", "fields"];

/// Page size used when a request does not ask for one.
pub const DEFAULT_LIMIT: usize = 20;

/// Largest page a server will serve, whatever the request asks for.
pub const MAX_LIMIT: usize = 100;

/// The query parameters of a request, in the order they were sent.
///
/// A name may repeat, which is how `?tag=a&tag=b` asks for either tag.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct QueryParams {
    entries: Vec<(String, String)>,
}

impl QueryParams {
    /// No parameters at all.
    pub fn new() -> Self {
        Self::default()
    }

    /// Parse a raw query string, with or without its leading `?`.
    ///
    /// # Examples
    ///
    /// ```
    /// use lino_rest_api::query::QueryParams;
    ///
    /// let query = QueryParams::parse("?tag=a&tag=b&limit=5");
    /// assert_eq!(query.get_all("tag"), vec!["a", "b"]);
    /// assert_eq!(query.get_last("limit"), Some("5"));
    /// ```
    pub fn parse(query_string: &str) -> Self {
        let trimmed = query_string.strip_prefix('?').unwrap_or(query_string);
        let mut entries = Vec::new();
        for pair in trimmed.split('&') {
            if pair.is_empty() {
                continue;
            }
            let (name, value) = match pair.split_once('=') {
                Some((name, value)) => (name, value),
                None => (pair, ""),
            };
            entries.push((form_decode(name), form_decode(value)));
        }
        Self { entries }
    }

    /// Add one parameter, keeping any parameter of the same name.
    pub fn append<N: Into<String>, V: Into<String>>(&mut self, name: N, value: V) {
        self.entries.push((name.into(), value.into()));
    }

    /// Every value sent for a name, in order.
    pub fn get_all(&self, name: &str) -> Vec<&str> {
        self.entries
            .iter()
            .filter(|(existing, _)| existing == name)
            .map(|(_, value)| value.as_str())
            .collect()
    }

    /// The last value sent for a name, which is the one a scalar parameter means.
    pub fn get_last(&self, name: &str) -> Option<&str> {
        self.entries
            .iter()
            .rev()
            .find(|(existing, _)| existing == name)
            .map(|(_, value)| value.as_str())
    }

    /// Whether a name was sent at all.
    pub fn contains(&self, name: &str) -> bool {
        self.get_last(name).is_some()
    }

    /// The parameters, in the order they were sent.
    pub fn iter(&self) -> impl Iterator<Item = (&str, &str)> {
        self.entries
            .iter()
            .map(|(name, value)| (name.as_str(), value.as_str()))
    }

    /// The distinct parameter names, in the order they first appeared.
    pub fn names(&self) -> Vec<&str> {
        let mut names: Vec<&str> = Vec::new();
        for (name, _) in &self.entries {
            if !names.contains(&name.as_str()) {
                names.push(name);
            }
        }
        names
    }

    /// Whether any parameter was sent.
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// How many parameters were sent, counting repetitions.
    pub fn len(&self) -> usize {
        self.entries.len()
    }

    /// Render the parameters back as a query string.
    pub fn to_query_string(&self) -> String {
        self.entries
            .iter()
            .map(|(name, value)| format!("{}={}", form_encode(name), form_encode(value)))
            .collect::<Vec<_>>()
            .join("&")
    }
}

/// Percent-encode one query component the way a form does, with `+` for a space.
pub fn form_encode(text: &str) -> String {
    let mut encoded = String::with_capacity(text.len());
    for byte in text.as_bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                encoded.push(*byte as char)
            }
            b' ' => encoded.push('+'),
            other => encoded.push_str(&format!("%{other:02X}")),
        }
    }
    encoded
}

/// Decode one query component, reading `+` as a space.
pub fn form_decode(text: &str) -> String {
    let bytes = text.as_bytes();
    let mut decoded: Vec<u8> = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        match bytes[index] {
            b'+' => {
                decoded.push(b' ');
                index += 1;
            }
            b'%' if index + 2 < bytes.len() => {
                match u8::from_str_radix(&text[index + 1..index + 3], 16) {
                    Ok(byte) => {
                        decoded.push(byte);
                        index += 3;
                    }
                    Err(_) => {
                        decoded.push(b'%');
                        index += 1;
                    }
                }
            }
            byte => {
                decoded.push(byte);
                index += 1;
            }
        }
    }
    String::from_utf8_lossy(&decoded).into_owned()
}

/// One ordering key of a collection query.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SortKey {
    /// Field the items are ordered by.
    pub field: String,
    /// Whether the order is descending.
    pub descending: bool,
}

/// One field filter: a name and the value, or values, it must equal.
#[derive(Debug, Clone, PartialEq)]
pub struct Filter {
    /// Field the items are filtered on.
    pub field: String,
    /// Accepted values; more than one means "any of these".
    pub values: Vec<LinoValue>,
}

/// A parsed collection query.
#[derive(Debug, Clone, PartialEq)]
pub struct CollectionQuery {
    /// Page size.
    pub limit: usize,
    /// Index of the first item of the page.
    pub offset: usize,
    /// Ordering keys, most significant first.
    pub sort: Vec<SortKey>,
    /// Sparse fieldset, or [`None`] when every field is requested.
    pub fields: Option<Vec<String>>,
    /// Field filters.
    pub filters: Vec<Filter>,
}

impl Default for CollectionQuery {
    fn default() -> Self {
        Self {
            limit: DEFAULT_LIMIT,
            offset: 0,
            sort: Vec::new(),
            fields: None,
            filters: Vec::new(),
        }
    }
}

/// Parse a filter value with the Links Notation scalar rules.
///
/// `?done=true` filters on the boolean, `?id=7` on the integer, and anything
/// else stays a string.
///
/// # Examples
///
/// ```
/// use lino_objects_codec::LinoValue;
/// use lino_rest_api::query::parse_scalar;
///
/// assert_eq!(parse_scalar("true"), LinoValue::Bool(true));
/// assert_eq!(parse_scalar("7"), LinoValue::Int(7));
/// assert_eq!(parse_scalar("seven"), LinoValue::String("seven".into()));
/// ```
pub fn parse_scalar(raw: &str) -> LinoValue {
    match raw {
        "true" => return LinoValue::Bool(true),
        "false" => return LinoValue::Bool(false),
        "null" => return LinoValue::Null,
        "" => return LinoValue::String(String::new()),
        _ => {}
    }
    if let Ok(number) = raw.parse::<i64>() {
        return LinoValue::Int(number);
    }
    if let Ok(number) = raw.parse::<f64>() {
        // Rust parses "inf" and "nan", which Links Notation has no spelling for,
        // so those stay the strings they were sent as.
        if number.is_finite() {
            return LinoValue::Float(number);
        }
    }
    LinoValue::String(raw.to_string())
}

/// Parse a bounded non-negative integer query parameter.
///
/// # Errors
///
/// A `400` when the value is not a non-negative integer.
pub fn parse_bounded_integer(
    raw: Option<&str>,
    fallback: usize,
    name: &str,
    maximum: Option<usize>,
) -> Result<usize, LinoHttpError> {
    let raw = match raw {
        None | Some("") => return Ok(fallback),
        Some(raw) => raw,
    };
    let value: usize = raw.parse().map_err(|_| {
        LinoHttpError::new(
            400,
            Some(&format!(
                "Query parameter \"{name}\" must be a non-negative integer"
            )),
        )
    })?;
    Ok(match maximum {
        Some(maximum) => value.min(maximum),
        None => value,
    })
}

/// Parse a `sort` parameter into ordered sort keys.
pub fn parse_sort(raw: Option<&str>) -> Vec<SortKey> {
    let Some(raw) = raw.filter(|raw| !raw.is_empty()) else {
        return Vec::new();
    };
    raw.split(',')
        .map(str::trim)
        .filter(|part| !part.is_empty())
        .map(|part| match part.strip_prefix('-') {
            Some(field) => SortKey {
                field: field.to_string(),
                descending: true,
            },
            None => SortKey {
                field: part.to_string(),
                descending: false,
            },
        })
        .collect()
}

/// Parse a `fields` parameter into a sparse fieldset.
pub fn parse_fields(raw: Option<&str>) -> Option<Vec<String>> {
    let raw = raw.filter(|raw| !raw.is_empty())?;
    let fields: Vec<String> = raw
        .split(',')
        .map(str::trim)
        .filter(|part| !part.is_empty())
        .map(str::to_string)
        .collect();
    if fields.is_empty() {
        None
    } else {
        Some(fields)
    }
}

/// Parse a full collection query from request query parameters.
///
/// # Errors
///
/// Whatever [`parse_bounded_integer`] refuses.
pub fn parse_collection_query(
    query: &QueryParams,
    default_limit: usize,
    max_limit: usize,
) -> Result<CollectionQuery, LinoHttpError> {
    let mut filters = Vec::new();
    for name in query.names() {
        if RESERVED_QUERY_PARAMETERS.contains(&name) {
            continue;
        }
        filters.push(Filter {
            field: name.to_string(),
            values: query.get_all(name).into_iter().map(parse_scalar).collect(),
        });
    }

    Ok(CollectionQuery {
        limit: parse_bounded_integer(
            query.get_last("limit"),
            default_limit,
            "limit",
            Some(max_limit),
        )?,
        offset: parse_bounded_integer(query.get_last("offset"), 0, "offset", None)?,
        sort: parse_sort(query.get_last("sort")),
        fields: parse_fields(query.get_last("fields")),
        filters,
    })
}
