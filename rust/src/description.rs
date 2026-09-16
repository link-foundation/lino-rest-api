//! Machine-readable service description (specification section 9).
//!
//! The same route registry is rendered twice: once as the native Links Notation
//! description served at `/.well-known/lino-api`, and once as an OpenAPI 3.1
//! document served at `/.well-known/openapi.json`, so that existing tooling keeps
//! working against a Links Notation API.

use lino_objects_codec::LinoValue;

use crate::media_type::supported_media_types;
use crate::router::RouteDescription;
use crate::value::{array, boolean, object, string};

/// Version of the description document this package emits.
pub const LINO_API_DESCRIPTION_VERSION: &str = "1.0";

/// Title, version and optional prose description of a service.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ServiceInfo {
    /// Human readable name of the service.
    pub title: String,
    /// Version of the service.
    pub version: String,
    /// Prose description, carried by both documents when present.
    pub description: Option<String>,
}

impl ServiceInfo {
    /// A service with a title and a version.
    pub fn new<T: Into<String>, V: Into<String>>(title: T, version: V) -> Self {
        Self {
            title: title.into(),
            version: version.into(),
            description: None,
        }
    }

    /// The same service carrying a prose description.
    ///
    /// # Examples
    ///
    /// ```
    /// use lino_rest_api::description::ServiceInfo;
    ///
    /// let info = ServiceInfo::new("Tasks API", "1.0.0").describing("A task list");
    /// assert_eq!(info.description.as_deref(), Some("A task list"));
    /// ```
    pub fn describing<D: Into<String>>(mut self, description: D) -> Self {
        self.description = Some(description.into());
        self
    }
}

/// The schema every Links Notation body is declared with.
fn lino_schema() -> LinoValue {
    object([
        (
            "description",
            string(
                "Links Notation document, see https://github.com/link-foundation/links-notation",
            ),
        ),
        ("type", string("string")),
    ])
}

/// Render the `info` member shared by both description documents.
///
/// The prose description appears only when there is one, so that a service
/// without one describes itself exactly as the JavaScript and Python packages do.
pub fn info_object(info: &ServiceInfo) -> LinoValue {
    let mut members = vec![
        ("title".to_string(), string(info.title.clone())),
        ("version".to_string(), string(info.version.clone())),
    ];
    if let Some(description) = info.description.as_deref().filter(|text| !text.is_empty()) {
        members.push(("description".to_string(), string(description)));
    }
    LinoValue::Object(members)
}

/// Render one route as it appears in the `routes` member.
fn route_object(route: &RouteDescription) -> LinoValue {
    let mut members = vec![
        ("path".to_string(), string(route.path.clone())),
        (
            "methods".to_string(),
            array(route.methods.iter().map(|method| string(method.clone()))),
        ),
    ];
    if let Some(summary) = route.summary.as_deref().filter(|text| !text.is_empty()) {
        members.push(("summary".to_string(), string(summary)));
    }
    LinoValue::Object(members)
}

/// Build the native service description.
///
/// # Examples
///
/// ```
/// use lino_rest_api::description::{service_description, ServiceInfo};
/// use lino_rest_api::value::get;
///
/// let document = service_description(&ServiceInfo::new("Tasks", "1.0.0"), &[], None);
/// assert_eq!(get(&document, "lino_api").and_then(lino_rest_api::value::as_str), Some("1.0"));
/// ```
pub fn service_description(
    info: &ServiceInfo,
    routes: &[RouteDescription],
    media_types: Option<&[String]>,
) -> LinoValue {
    let types = media_types
        .map(<[String]>::to_vec)
        .unwrap_or_else(supported_media_types);
    object([
        ("lino_api", string(LINO_API_DESCRIPTION_VERSION)),
        ("info", info_object(info)),
        ("media_types", array(types.into_iter().map(string))),
        ("routes", array(routes.iter().map(route_object))),
    ])
}

/// Convert a `:parameter` path to the OpenAPI template syntax.
///
/// # Examples
///
/// ```
/// use lino_rest_api::description::to_openapi_path;
///
/// assert_eq!(to_openapi_path("/items/:id/tags/:tag"), "/items/{id}/tags/{tag}");
/// ```
pub fn to_openapi_path(path: &str) -> String {
    path.split('/')
        .map(|segment| match segment.strip_prefix(':') {
            Some(name) if is_parameter_name(name) => format!("{{{name}}}"),
            _ => segment.to_string(),
        })
        .collect::<Vec<_>>()
        .join("/")
}

/// Extract the path parameters of a path pattern.
pub fn path_parameters(path: &str) -> Vec<String> {
    path.split('/')
        .filter_map(|segment| segment.strip_prefix(':'))
        .filter(|name| is_parameter_name(name))
        .map(str::to_string)
        .collect()
}

/// Whether a name may be used as a path parameter.
fn is_parameter_name(name: &str) -> bool {
    !name.is_empty()
        && name
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || character == '_')
}

/// Build an OpenAPI 3.1 document describing the service.
///
/// Every request and response body is declared for all negotiable media types,
/// so that a generated client knows it may ask for `text/lino`.
pub fn openapi_document(
    info: &ServiceInfo,
    routes: &[RouteDescription],
    media_types: Option<&[String]>,
) -> LinoValue {
    let types = media_types
        .map(<[String]>::to_vec)
        .unwrap_or_else(supported_media_types);
    let content = LinoValue::Object(
        types
            .iter()
            .map(|media_type| (media_type.clone(), object([("schema", lino_schema())])))
            .collect(),
    );

    let mut paths: Vec<(String, LinoValue)> = Vec::new();
    for route in routes {
        let template = to_openapi_path(&route.path);
        let parameters: Vec<LinoValue> = path_parameters(&route.path)
            .into_iter()
            .map(|name| {
                object([
                    ("name", string(name)),
                    ("in", string("path")),
                    ("required", boolean(true)),
                    ("schema", object([("type", string("string"))])),
                ])
            })
            .collect();

        let mut operations: Vec<(String, LinoValue)> = Vec::new();
        for method in &route.methods {
            let summary = route
                .summary
                .clone()
                .filter(|text| !text.is_empty())
                .unwrap_or_else(|| format!("{method} {}", route.path));
            let mut operation = vec![
                ("summary".to_string(), string(summary)),
                (
                    "responses".to_string(),
                    object([
                        (
                            "200",
                            object([
                                ("description", string("Success")),
                                ("content", content.clone()),
                            ]),
                        ),
                        (
                            "default",
                            object([
                                (
                                    "description",
                                    string("RFC 9457 problem details in Links Notation"),
                                ),
                                ("content", content.clone()),
                            ]),
                        ),
                    ]),
                ),
            ];
            if !parameters.is_empty() {
                operation.push((
                    "parameters".to_string(),
                    LinoValue::Array(parameters.clone()),
                ));
            }
            if matches!(method.as_str(), "POST" | "PUT" | "PATCH") {
                operation.push((
                    "requestBody".to_string(),
                    object([("required", boolean(true)), ("content", content.clone())]),
                ));
            }
            operations.push((method.to_lowercase(), LinoValue::Object(operation)));
        }
        paths.push((template, LinoValue::Object(operations)));
    }

    object([
        ("openapi", string("3.1.0")),
        ("info", info_object(info)),
        ("paths", LinoValue::Object(paths)),
    ])
}
