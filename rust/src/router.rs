//! Route registry backing automatic `HEAD`, automatic `OPTIONS`, `405 Method Not
//! Allowed` and the service description (specification sections 4.1 and 9).
//!
//! Path patterns use the `:parameter` syntax of the JavaScript and Python
//! implementations, so the same route table is described identically in all
//! three languages.

use std::collections::BTreeMap;

/// Methods that never need to be registered explicitly.
pub const IMPLICIT_METHODS: [&str; 2] = ["HEAD", "OPTIONS"];

/// Description metadata attached to one method of one route.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct RouteMeta {
    /// One-line summary, shown in both description documents.
    pub summary: Option<String>,
}

impl RouteMeta {
    /// Metadata carrying only a summary.
    pub fn summary<S: Into<String>>(summary: S) -> Self {
        Self {
            summary: Some(summary.into()),
        }
    }
}

/// The path parameters captured by a match.
pub type PathParams = BTreeMap<String, String>;

/// Every method registered on one path pattern.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RouteEntry {
    /// The pattern the route was registered with.
    pub pattern: String,
    /// Methods registered on it, in registration order.
    pub methods: Vec<(String, RouteMeta)>,
}

impl RouteEntry {
    /// Whether a method is registered on this route.
    pub fn has_method(&self, method: &str) -> bool {
        self.methods.iter().any(|(name, _)| name == method)
    }
}

/// Split a path or a pattern into its segments, ignoring one trailing slash.
fn segments(path: &str) -> Vec<&str> {
    let trimmed = if path.len() > 1 {
        path.strip_suffix('/').unwrap_or(path)
    } else {
        path
    };
    trimmed.split('/').collect()
}

/// Match a concrete path against a pattern, capturing its path parameters.
///
/// A `:name` segment captures one non-empty segment, and a `*` segment captures
/// everything left, including slashes.
///
/// # Examples
///
/// ```
/// use lino_rest_api::router::match_path;
///
/// let params = match_path("/tasks/:id", "/tasks/7").unwrap();
/// assert_eq!(params["id"], "7");
/// assert!(match_path("/tasks/:id", "/tasks").is_none());
/// ```
pub fn match_path(pattern: &str, pathname: &str) -> Option<PathParams> {
    let pattern_segments = segments(pattern);
    let path_segments = segments(pathname);
    let mut params = PathParams::new();

    for (index, expected) in pattern_segments.iter().enumerate() {
        if let Some(name) = expected.strip_prefix('*') {
            // A wildcard swallows the rest of the path, named when it is named.
            let rest = path_segments.get(index..).unwrap_or(&[]).join("/");
            if !name.is_empty() {
                params.insert(name.to_string(), rest);
            }
            return Some(params);
        }
        let actual = path_segments.get(index)?;
        match expected.strip_prefix(':') {
            Some(name) => {
                if actual.is_empty() {
                    return None;
                }
                params.insert(name.to_string(), (*actual).to_string());
            }
            None => {
                if expected != actual {
                    return None;
                }
            }
        }
    }

    if path_segments.len() > pattern_segments.len() {
        return None;
    }
    Some(params)
}

/// The set of routes registered on an application.
#[derive(Debug, Clone, Default)]
pub struct RouteTable {
    routes: Vec<RouteEntry>,
}

impl RouteTable {
    /// An empty table.
    pub fn new() -> Self {
        Self::default()
    }

    /// Register a method on a path.
    ///
    /// Registering the same method twice replaces its metadata, which is how a
    /// route is redefined.
    pub fn register(&mut self, method: &str, pattern: &str, meta: RouteMeta) {
        let method = method.to_uppercase();
        let entry = match self
            .routes
            .iter_mut()
            .position(|entry| entry.pattern == pattern)
        {
            Some(index) => &mut self.routes[index],
            None => {
                self.routes.push(RouteEntry {
                    pattern: pattern.to_string(),
                    methods: Vec::new(),
                });
                self.routes.last_mut().expect("just pushed")
            }
        };
        match entry.methods.iter_mut().find(|(name, _)| *name == method) {
            Some(existing) => existing.1 = meta,
            None => entry.methods.push((method, meta)),
        }
    }

    /// Remove a method from a path, dropping the path when it keeps none.
    ///
    /// Used by [`crate::app::LinoApp::without_description`] to withdraw the
    /// description routes the constructor registers.
    pub fn remove(&mut self, method: &str, pattern: &str) {
        let method = method.to_uppercase();
        let Some(index) = self
            .routes
            .iter()
            .position(|entry| entry.pattern == pattern)
        else {
            return;
        };
        self.routes[index]
            .methods
            .retain(|(name, _)| *name != method);
        if self.routes[index].methods.is_empty() {
            self.routes.remove(index);
        }
    }

    /// Find the route entry owning a concrete path.
    pub fn find(&self, pathname: &str) -> Option<&RouteEntry> {
        self.match_path(pathname).map(|(entry, _)| entry)
    }

    /// Find the route entry owning a path together with its path parameters.
    ///
    /// Routes are tried in registration order, so an earlier registration wins.
    pub fn match_path(&self, pathname: &str) -> Option<(&RouteEntry, PathParams)> {
        self.routes
            .iter()
            .find_map(|entry| match_path(&entry.pattern, pathname).map(|params| (entry, params)))
    }

    /// List the methods allowed on a concrete path.
    ///
    /// `OPTIONS` is always allowed, and `HEAD` is allowed wherever `GET` is.
    /// The answer is [`None`] when no route owns the path.
    pub fn allowed_methods(&self, pathname: &str) -> Option<Vec<String>> {
        let entry = self.find(pathname)?;
        Some(self.allowed_methods_of(entry))
    }

    /// The methods allowed on a route entry, sorted.
    pub fn allowed_methods_of(&self, entry: &RouteEntry) -> Vec<String> {
        let mut methods: Vec<String> = entry.methods.iter().map(|(name, _)| name.clone()).collect();
        if methods.iter().any(|method| method == "GET") && !methods.iter().any(|m| m == "HEAD") {
            methods.push("HEAD".to_string());
        }
        if !methods.iter().any(|method| method == "OPTIONS") {
            methods.push("OPTIONS".to_string());
        }
        methods.sort();
        methods.dedup();
        methods
    }

    /// The registered routes, in registration order.
    pub fn entries(&self) -> &[RouteEntry] {
        &self.routes
    }

    /// Render the registry as the `routes` member of a service description.
    ///
    /// Routes are ordered by path, so two servers describing the same routes
    /// describe them identically.
    pub fn describe(&self) -> Vec<RouteDescription> {
        let mut descriptions: Vec<RouteDescription> = self
            .routes
            .iter()
            .map(|entry| RouteDescription {
                path: entry.pattern.clone(),
                methods: self.allowed_methods_of(entry),
                summary: entry
                    .methods
                    .iter()
                    .find_map(|(_, meta)| meta.summary.clone()),
            })
            .collect();
        descriptions.sort_by(|left, right| left.path.cmp(&right.path));
        descriptions
    }
}

/// One route of a service description.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RouteDescription {
    /// Path pattern.
    pub path: String,
    /// Methods allowed on it.
    pub methods: Vec<String>,
    /// One-line summary, when the route carries one.
    pub summary: Option<String>,
}
