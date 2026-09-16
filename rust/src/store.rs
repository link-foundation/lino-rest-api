//! The store interface a resource is built on, and an in-memory implementation.
//!
//! A store is anything that can list, read, create, replace, merge and delete
//! items; [`MemoryStore`] is the built-in one, so that a working CRUD API is one
//! call away in examples, tests and prototypes.

use std::sync::Mutex;

use async_trait::async_trait;
use lino_objects_codec::LinoValue;

use crate::collection::apply_collection_query;
use crate::problem::LinoHttpError;
use crate::query::CollectionQuery;
use crate::value::{as_object, get, merge, set};

/// What a store must be able to do for [`crate::resource::register_resource`].
///
/// Every method is asynchronous, so a store may read from a database, and every
/// one may fail with a [`LinoHttpError`], so a store may refuse a write with any
/// status it likes.
#[async_trait]
pub trait Store: Send + Sync {
    /// The field of an item that holds its identifier.
    fn id_field(&self) -> &str {
        "id"
    }

    /// Run a collection query, returning a collection envelope.
    async fn list(&self, query: &CollectionQuery) -> Result<LinoValue, LinoHttpError>;

    /// Read one item, or [`None`] when it does not exist.
    async fn get(&self, identifier: &str) -> Result<Option<LinoValue>, LinoHttpError>;

    /// Create an item, assigning an identifier when the body carries none.
    async fn create(&self, body: &LinoValue) -> Result<LinoValue, LinoHttpError>;

    /// Replace an item, or [`None`] when it does not exist.
    async fn update(
        &self,
        identifier: &str,
        body: &LinoValue,
    ) -> Result<Option<LinoValue>, LinoHttpError>;

    /// Merge changes into an item, or [`None`] when it does not exist.
    async fn patch(
        &self,
        identifier: &str,
        body: &LinoValue,
    ) -> Result<Option<LinoValue>, LinoHttpError>;

    /// Delete an item, reporting whether one was deleted.
    async fn remove(&self, identifier: &str) -> Result<bool, LinoHttpError>;
}

/// Normalise an identifier so that `"1"` from a path matches a stored `1`.
///
/// # Examples
///
/// ```
/// use lino_objects_codec::LinoValue;
/// use lino_rest_api::store::normalize_id;
///
/// assert_eq!(normalize_id("1"), LinoValue::Int(1));
/// assert_eq!(normalize_id("abc"), LinoValue::String("abc".into()));
/// ```
pub fn normalize_id(identifier: &str) -> LinoValue {
    match identifier.parse::<i64>() {
        Ok(number) if !identifier.is_empty() => LinoValue::Int(number),
        _ => LinoValue::String(identifier.to_string()),
    }
}

/// Normalise an identifier that is already a value.
fn normalize_value_id(identifier: &LinoValue) -> LinoValue {
    match identifier {
        LinoValue::String(text) => normalize_id(text),
        other => other.clone(),
    }
}

/// Render an identifier as the text a path carries.
pub fn id_to_string(identifier: &LinoValue) -> String {
    crate::value::to_query_text(identifier)
}

/// A resource store backed by an ordered list of items.
///
/// Items keep the order they were created in, which is the order the collection
/// lists them in when no `sort` is asked for.
#[derive(Debug, Default)]
pub struct MemoryStore {
    id_field: String,
    state: Mutex<MemoryState>,
}

#[derive(Debug, Default)]
struct MemoryState {
    items: Vec<(LinoValue, LinoValue)>,
    next_id: i64,
}

impl MemoryStore {
    /// An empty store whose identifier field is `id`.
    pub fn new() -> Self {
        Self {
            id_field: "id".to_string(),
            state: Mutex::new(MemoryState {
                items: Vec::new(),
                next_id: 1,
            }),
        }
    }

    /// An empty store whose identifier field has another name.
    pub fn with_id_field<S: Into<String>>(id_field: S) -> Self {
        Self {
            id_field: id_field.into(),
            ..Self::new()
        }
    }

    /// A store seeded with items.
    ///
    /// # Examples
    ///
    /// ```
    /// use lino_rest_api::store::MemoryStore;
    /// use lino_rest_api::value::{get, int, object, string};
    ///
    /// let store = MemoryStore::seeded([object([("title", string("Ship it"))])]);
    /// assert_eq!(get(&store.read("1").unwrap(), "id"), Some(&int(1)));
    /// ```
    pub fn seeded<I: IntoIterator<Item = LinoValue>>(items: I) -> Self {
        let store = Self::new();
        for item in items {
            store.insert(&item);
        }
        store
    }

    /// Create an item without awaiting, for seeding and for tests.
    pub fn insert(&self, body: &LinoValue) -> LinoValue {
        let mut state = self.state.lock().expect("store is not poisoned");
        let identifier = match get(body, &self.id_field) {
            Some(LinoValue::Null) | None => {
                let identifier = LinoValue::Int(state.next_id);
                state.next_id += 1;
                identifier
            }
            Some(provided) => normalize_value_id(provided),
        };
        if let LinoValue::Int(number) = identifier {
            if number >= state.next_id {
                state.next_id = number + 1;
            }
        }

        let mut item = if matches!(body, LinoValue::Object(_)) {
            body.clone()
        } else {
            LinoValue::Object(Vec::new())
        };
        set(&mut item, self.id_field.clone(), identifier.clone());

        match state.items.iter_mut().find(|(key, _)| *key == identifier) {
            Some(entry) => entry.1 = item.clone(),
            None => state.items.push((identifier, item.clone())),
        }
        item
    }

    /// Read an item without awaiting, for tests.
    pub fn read(&self, identifier: &str) -> Option<LinoValue> {
        let key = normalize_id(identifier);
        let state = self.state.lock().expect("store is not poisoned");
        state
            .items
            .iter()
            .find(|(existing, _)| *existing == key)
            .map(|(_, item)| item.clone())
    }

    /// Every item, in creation order.
    pub fn items(&self) -> Vec<LinoValue> {
        let state = self.state.lock().expect("store is not poisoned");
        state.items.iter().map(|(_, item)| item.clone()).collect()
    }

    /// How many items the store holds.
    pub fn len(&self) -> usize {
        self.state
            .lock()
            .expect("store is not poisoned")
            .items
            .len()
    }

    /// Whether the store holds no item.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Remove every item and restart the identifier sequence.
    pub fn clear(&self) {
        let mut state = self.state.lock().expect("store is not poisoned");
        state.items.clear();
        state.next_id = 1;
    }

    /// Replace the item at an identifier, or report that there is none.
    fn replace(&self, identifier: &str, item: LinoValue) -> Option<LinoValue> {
        let key = normalize_id(identifier);
        let mut state = self.state.lock().expect("store is not poisoned");
        let entry = state
            .items
            .iter_mut()
            .find(|(existing, _)| *existing == key)?;
        entry.1 = item.clone();
        Some(item)
    }
}

#[async_trait]
impl Store for MemoryStore {
    fn id_field(&self) -> &str {
        &self.id_field
    }

    async fn list(&self, query: &CollectionQuery) -> Result<LinoValue, LinoHttpError> {
        Ok(apply_collection_query(&self.items(), query))
    }

    async fn get(&self, identifier: &str) -> Result<Option<LinoValue>, LinoHttpError> {
        Ok(self.read(identifier))
    }

    async fn create(&self, body: &LinoValue) -> Result<LinoValue, LinoHttpError> {
        Ok(self.insert(body))
    }

    async fn update(
        &self,
        identifier: &str,
        body: &LinoValue,
    ) -> Result<Option<LinoValue>, LinoHttpError> {
        if self.read(identifier).is_none() {
            return Ok(None);
        }
        let mut item = if as_object(body).is_some() {
            body.clone()
        } else {
            LinoValue::Object(Vec::new())
        };
        set(&mut item, self.id_field.clone(), normalize_id(identifier));
        Ok(self.replace(identifier, item))
    }

    async fn patch(
        &self,
        identifier: &str,
        body: &LinoValue,
    ) -> Result<Option<LinoValue>, LinoHttpError> {
        let Some(existing) = self.read(identifier) else {
            return Ok(None);
        };
        let mut item = merge(&existing, body);
        set(&mut item, self.id_field.clone(), normalize_id(identifier));
        Ok(self.replace(identifier, item))
    }

    async fn remove(&self, identifier: &str) -> Result<bool, LinoHttpError> {
        let key = normalize_id(identifier);
        let mut state = self.state.lock().expect("store is not poisoned");
        match state
            .items
            .iter()
            .position(|(existing, _)| *existing == key)
        {
            Some(index) => {
                state.items.remove(index);
                Ok(true)
            }
            None => Ok(false),
        }
    }
}
