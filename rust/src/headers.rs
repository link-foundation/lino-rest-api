//! A small, case-insensitive header map that keeps insertion order.
//!
//! HTTP field names are case-insensitive, but the order in which a response
//! writes them is worth keeping stable, so that two runs of the same request
//! produce the same bytes on the wire.

use std::fmt;

/// Header fields, looked up without regard to case and written in the order
/// they were set.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Headers {
    entries: Vec<(String, String)>,
}

impl Headers {
    /// An empty map.
    pub fn new() -> Self {
        Self::default()
    }

    /// Build a map from pairs, later pairs replacing earlier ones.
    ///
    /// # Examples
    ///
    /// ```
    /// use lino_rest_api::headers::Headers;
    ///
    /// let headers = Headers::from_pairs([("Content-Type", "text/lino")]);
    /// assert_eq!(headers.get("content-type"), Some("text/lino"));
    /// ```
    pub fn from_pairs<I, N, V>(pairs: I) -> Self
    where
        I: IntoIterator<Item = (N, V)>,
        N: Into<String>,
        V: Into<String>,
    {
        let mut headers = Self::new();
        for (name, value) in pairs {
            headers.insert(name, value);
        }
        headers
    }

    /// The value of a field, or [`None`] when it is absent.
    pub fn get(&self, name: &str) -> Option<&str> {
        self.entries
            .iter()
            .find(|(existing, _)| existing.eq_ignore_ascii_case(name))
            .map(|(_, value)| value.as_str())
    }

    /// Whether a field is present.
    pub fn contains(&self, name: &str) -> bool {
        self.get(name).is_some()
    }

    /// Set a field, replacing any existing one and keeping its position.
    pub fn insert<N: Into<String>, V: Into<String>>(&mut self, name: N, value: V) {
        let name = name.into();
        let value = value.into();
        match self
            .entries
            .iter_mut()
            .find(|(existing, _)| existing.eq_ignore_ascii_case(&name))
        {
            Some(entry) => entry.1 = value,
            None => self.entries.push((name, value)),
        }
    }

    /// Set a field only when it is absent, which is how defaults are applied.
    pub fn insert_missing<N: Into<String>, V: Into<String>>(&mut self, name: N, value: V) {
        let name = name.into();
        if !self.contains(&name) {
            self.insert(name, value);
        }
    }

    /// Remove a field, returning its value when there was one.
    pub fn remove(&mut self, name: &str) -> Option<String> {
        let index = self
            .entries
            .iter()
            .position(|(existing, _)| existing.eq_ignore_ascii_case(name))?;
        Some(self.entries.remove(index).1)
    }

    /// Whether the map carries no field.
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// How many fields the map carries.
    pub fn len(&self) -> usize {
        self.entries.len()
    }

    /// The fields, in the order they were set.
    pub fn iter(&self) -> impl Iterator<Item = (&str, &str)> {
        self.entries
            .iter()
            .map(|(name, value)| (name.as_str(), value.as_str()))
    }

    /// Merge fields from another map, without overwriting what is already set.
    pub fn extend_missing(&mut self, other: &Headers) {
        for (name, value) in other.iter() {
            self.insert_missing(name.to_string(), value.to_string());
        }
    }
}

impl<'a> IntoIterator for &'a Headers {
    type Item = (&'a str, &'a str);
    type IntoIter = Box<dyn Iterator<Item = (&'a str, &'a str)> + 'a>;

    fn into_iter(self) -> Self::IntoIter {
        Box::new(self.iter())
    }
}

impl fmt::Display for Headers {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        for (name, value) in self.iter() {
            writeln!(formatter, "{name}: {value}")?;
        }
        Ok(())
    }
}

/// Append a field value to a comma-separated list, without repeating it.
///
/// This is how `Vary` collects `Accept` and `Origin` (specification section 3).
///
/// # Examples
///
/// ```
/// use lino_rest_api::headers::{append_list_value, Headers};
///
/// let mut headers = Headers::from_pairs([("Vary", "Accept")]);
/// append_list_value(&mut headers, "Vary", "Origin");
/// assert_eq!(headers.get("Vary"), Some("Accept, Origin"));
/// ```
pub fn append_list_value(headers: &mut Headers, name: &str, value: &str) {
    match headers.get(name) {
        None => headers.insert(name.to_string(), value.to_string()),
        Some(existing) => {
            let already = existing
                .split(',')
                .any(|part| part.trim().eq_ignore_ascii_case(value));
            if !already {
                let merged = format!("{existing}, {value}");
                headers.insert(name.to_string(), merged);
            }
        }
    }
}
