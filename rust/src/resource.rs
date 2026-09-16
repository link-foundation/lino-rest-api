//! CRUD resource registration.
//!
//! Turns a [`Store`] into the six routes the specification describes for a
//! collection and its items, including pagination `Link` headers (section 6.1),
//! entity tags and conditional requests (section 7).

use std::sync::Arc;

use lino_objects_codec::LinoValue;

use crate::app::LinoApp;
use crate::codec::encode_for;
use crate::collection::pagination_link_header;
use crate::etag::{compute_etag, evaluate_preconditions};
use crate::problem::LinoHttpError;
use crate::request::{LinoRequest, percent_encode};
use crate::response::{Body, LinoResult, created, no_content, ok};
use crate::store::Store;
use crate::value::{get, to_query_text, with};

/// Operations a resource can expose, in registration order.
pub const RESOURCE_OPERATIONS: [&str; 6] = ["list", "create", "get", "update", "patch", "remove"];

/// How a resource is registered.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResourceOptions {
    /// Path parameter holding the identifier.
    pub id_param: String,
    /// Field of an item holding the identifier; [`None`] asks the store.
    pub id_field: Option<String>,
    /// Human readable name used in problem details.
    pub name: Option<String>,
    /// Subset of [`RESOURCE_OPERATIONS`] to expose.
    pub operations: Vec<String>,
    /// Demand `If-Match` on `PUT`, `PATCH` and `DELETE`.
    pub require_precondition: bool,
    /// Let `PUT` create a missing item.
    pub upsert: bool,
}

impl Default for ResourceOptions {
    fn default() -> Self {
        Self {
            id_param: "id".to_string(),
            id_field: None,
            name: None,
            operations: RESOURCE_OPERATIONS.iter().map(|s| s.to_string()).collect(),
            require_precondition: false,
            upsert: false,
        }
    }
}

impl ResourceOptions {
    /// The default options.
    pub fn new() -> Self {
        Self::default()
    }

    /// The same options with a human readable resource name.
    pub fn with_name<S: Into<String>>(mut self, name: S) -> Self {
        self.name = Some(name.into());
        self
    }

    /// The same options with another path parameter for the identifier.
    pub fn with_id_param<S: Into<String>>(mut self, id_param: S) -> Self {
        self.id_param = id_param.into();
        self
    }

    /// The same options with another identifier field.
    pub fn with_id_field<S: Into<String>>(mut self, id_field: S) -> Self {
        self.id_field = Some(id_field.into());
        self
    }

    /// The same options exposing only these operations.
    pub fn with_operations<I, S>(mut self, operations: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: Into<String>,
    {
        self.operations = operations.into_iter().map(Into::into).collect();
        self
    }

    /// The same options demanding `If-Match` on every unsafe method.
    pub fn requiring_precondition(mut self, require: bool) -> Self {
        self.require_precondition = require;
        self
    }

    /// The same options letting `PUT` create a missing item.
    pub fn with_upsert(mut self, upsert: bool) -> Self {
        self.upsert = upsert;
        self
    }

    /// Whether an operation is exposed.
    fn exposes(&self, operation: &str) -> bool {
        self.operations.iter().any(|name| name == operation)
    }
}

/// Entity tag of a value in the representation the client asked for.
///
/// Entity tags are per representation, which is why the negotiated media type is
/// part of the computation and why every response carries `Vary: Accept`.
///
/// # Errors
///
/// A `500` when the value cannot be encoded as the negotiated representation.
pub fn representation_etag(
    request: &LinoRequest,
    value: &LinoValue,
) -> Result<String, LinoHttpError> {
    let encoded = encode_for(value, &request.media_type)
        .map_err(|error| LinoHttpError::new(500, Some(&error.to_string())))?;
    Ok(compute_etag(&encoded))
}

/// The `404` raised when an item does not exist.
fn not_found(name: &str, identifier: &str) -> LinoHttpError {
    LinoHttpError::new(404, Some(&format!("{name} {identifier} does not exist")))
}

/// Read a page member of a collection envelope.
fn page_number(envelope: &LinoValue, key: &str) -> usize {
    match get(envelope, "page").and_then(|page| get(page, key)) {
        Some(LinoValue::Int(number)) if *number >= 0 => *number as usize,
        _ => 0,
    }
}

/// The URL of one item of a collection.
fn item_location(base_path: &str, identifier: &LinoValue) -> String {
    format!("{base_path}/{}", percent_encode(&to_query_text(identifier)))
}

/// Read the current item and evaluate `If-Match` against it before mutating.
///
/// Conditional requests on unsafe methods are about the representation that is
/// *being replaced*, so the check happens here rather than on the response.
///
/// # Errors
///
/// A `412` or a `428` when the precondition fails, and whatever the store reports.
async fn load_for_write(
    store: &dyn Store,
    request: &LinoRequest,
    identifier: &str,
    require_precondition: bool,
) -> Result<Option<LinoValue>, LinoHttpError> {
    let Some(existing) = store.get(identifier).await? else {
        return Ok(None);
    };
    evaluate_preconditions(
        &request.headers,
        &request.method,
        &representation_etag(request, &existing)?,
        require_precondition,
    )?;
    Ok(Some(existing))
}

/// Register the routes of a CRUD resource on an application.
///
/// # Examples
///
/// ```
/// use std::sync::Arc;
///
/// use lino_rest_api::app::{LinoApp, RawRequest};
/// use lino_rest_api::resource::ResourceOptions;
/// use lino_rest_api::store::MemoryStore;
/// use lino_rest_api::value::{object, string};
///
/// # tokio_test::block_on(async {
/// let store = Arc::new(MemoryStore::seeded([object([("title", string("Ship it"))])]));
/// let mut app = LinoApp::new();
/// app.resource("/tasks", store, ResourceOptions::new().with_name("task"));
///
/// let response = app.respond(RawRequest::new("GET", "/tasks/1")).await;
/// assert_eq!(response.status, 200);
/// assert!(response.body.contains("Ship it"));
/// # });
/// ```
pub fn register_resource<S: Store + 'static>(
    app: &mut LinoApp,
    base_path: &str,
    store: Arc<S>,
    options: ResourceOptions,
) {
    let field = options
        .id_field
        .clone()
        .unwrap_or_else(|| store.id_field().to_string());
    let name = options
        .name
        .clone()
        .unwrap_or_else(|| base_path.trim_matches('/').to_string());
    let item_path = format!("{base_path}/:{}", options.id_param);
    let base_path = base_path.to_string();

    if options.exposes("list") {
        let store = store.clone();
        app.get(
            &base_path,
            &format!("List {name}"),
            move |request: LinoRequest| {
                let store = store.clone();
                async move {
                    let query = request.collection_query()?;
                    let envelope = store.list(&query).await?;
                    let link = pagination_link_header(
                        &request.path,
                        &request.query(),
                        page_number(&envelope, "limit"),
                        page_number(&envelope, "offset"),
                        page_number(&envelope, "total"),
                    );
                    let result = ok(envelope);
                    Ok(if link.is_empty() {
                        result
                    } else {
                        result.with_header("Link", link)
                    })
                }
            },
        );
    }

    if options.exposes("create") {
        let store = store.clone();
        let field = field.clone();
        let base = base_path.clone();
        app.post(
            &base_path,
            &format!("Create {name}"),
            move |request: LinoRequest| {
                let store = store.clone();
                let field = field.clone();
                let base = base.clone();
                async move {
                    let body = request.require_body()?.clone();
                    let item = store.create(&body).await?;
                    let location = match get(&item, &field) {
                        Some(LinoValue::Null) | None => None,
                        Some(identifier) => Some(item_location(&base, identifier)),
                    };
                    Ok(match location {
                        Some(location) => created(item, &location),
                        None => LinoResult::new(201, Body::Value(item)),
                    })
                }
            },
        );
    }

    if options.exposes("get") {
        let store = store.clone();
        let name = name.clone();
        let id_param = options.id_param.clone();
        app.get(
            &item_path,
            &format!("Read one {name}"),
            move |request: LinoRequest| {
                let store = store.clone();
                let name = name.clone();
                let id_param = id_param.clone();
                async move {
                    let identifier = request.param(&id_param).unwrap_or_default();
                    store
                        .get(&identifier)
                        .await?
                        .ok_or_else(|| not_found(&name, &identifier))
                }
            },
        );
    }

    if options.exposes("update") {
        let store = store.clone();
        let name = name.clone();
        let field = field.clone();
        let base = base_path.clone();
        let id_param = options.id_param.clone();
        let require_precondition = options.require_precondition;
        let upsert = options.upsert;
        app.put(
            &item_path,
            &format!("Replace one {name}"),
            move |request: LinoRequest| {
                let store = store.clone();
                let name = name.clone();
                let field = field.clone();
                let base = base.clone();
                let id_param = id_param.clone();
                async move {
                    let body = request.require_body()?.clone();
                    let identifier = request.param(&id_param).unwrap_or_default();
                    let existing =
                        load_for_write(&*store, &request, &identifier, require_precondition)
                            .await?;
                    if existing.is_none() {
                        if !upsert {
                            return Err(not_found(&name, &identifier));
                        }
                        let seeded = with(
                            &body,
                            field.clone(),
                            crate::store::normalize_id(&identifier),
                        );
                        let item = store.create(&seeded).await?;
                        let location = match get(&item, &field) {
                            Some(LinoValue::Null) | None => {
                                item_location(&base, &crate::value::string(identifier))
                            }
                            Some(value) => item_location(&base, value),
                        };
                        return Ok(created(item, &location));
                    }
                    store
                        .update(&identifier, &body)
                        .await?
                        .map(ok)
                        .ok_or_else(|| not_found(&name, &identifier))
                }
            },
        );
    }

    if options.exposes("patch") {
        let store = store.clone();
        let name = name.clone();
        let id_param = options.id_param.clone();
        let require_precondition = options.require_precondition;
        app.patch(
            &item_path,
            &format!("Merge changes into one {name}"),
            move |request: LinoRequest| {
                let store = store.clone();
                let name = name.clone();
                let id_param = id_param.clone();
                async move {
                    let body = request.require_body()?.clone();
                    let identifier = request.param(&id_param).unwrap_or_default();
                    if load_for_write(&*store, &request, &identifier, require_precondition)
                        .await?
                        .is_none()
                    {
                        return Err(not_found(&name, &identifier));
                    }
                    store
                        .patch(&identifier, &body)
                        .await?
                        .map(ok)
                        .ok_or_else(|| not_found(&name, &identifier))
                }
            },
        );
    }

    if options.exposes("remove") {
        let store = store.clone();
        let name = name.clone();
        let id_param = options.id_param.clone();
        let require_precondition = options.require_precondition;
        app.delete(
            &item_path,
            &format!("Delete one {name}"),
            move |request: LinoRequest| {
                let store = store.clone();
                let name = name.clone();
                let id_param = id_param.clone();
                async move {
                    let identifier = request.param(&id_param).unwrap_or_default();
                    if load_for_write(&*store, &request, &identifier, require_precondition)
                        .await?
                        .is_none()
                    {
                        return Err(not_found(&name, &identifier));
                    }
                    store.remove(&identifier).await?;
                    Ok(no_content())
                }
            },
        );
    }
}
