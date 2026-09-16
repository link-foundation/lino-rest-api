//! Collection envelope, in-memory query execution and RFC 8288 link headers
//! (specification section 6).

use lino_objects_codec::LinoValue;

use crate::query::{CollectionQuery, Filter, QueryParams, SortKey, form_encode};
use crate::value::{array, compare, get, int, object};

/// Test whether an item satisfies every filter.
///
/// A filter carrying more than one value matches when the item field equals any
/// of them, which is what repeated query parameters (`?tag=a&tag=b`) mean.
pub fn matches_filters(item: &LinoValue, filters: &[Filter]) -> bool {
    filters.iter().all(|filter| {
        let actual = get(item, &filter.field).cloned().unwrap_or(LinoValue::Null);
        filter.values.contains(&actual)
    })
}

/// Sort items by the sort keys of a collection query.
///
/// The original list is left untouched, and the sort is stable, so items that
/// compare equal keep the order the store returned them in.
pub fn sort_items(items: &[LinoValue], sort: &[SortKey]) -> Vec<LinoValue> {
    let mut sorted = items.to_vec();
    if sort.is_empty() {
        return sorted;
    }
    sorted.sort_by(|left, right| {
        for key in sort {
            let left_value = get(left, &key.field).cloned().unwrap_or(LinoValue::Null);
            let right_value = get(right, &key.field).cloned().unwrap_or(LinoValue::Null);
            let comparison = compare(&left_value, &right_value);
            if comparison != std::cmp::Ordering::Equal {
                return if key.descending {
                    comparison.reverse()
                } else {
                    comparison
                };
            }
        }
        std::cmp::Ordering::Equal
    });
    sorted
}

/// Reduce an item to a sparse fieldset.
pub fn project_fields(item: &LinoValue, fields: Option<&Vec<String>>) -> LinoValue {
    let Some(fields) = fields else {
        return item.clone();
    };
    let Some(members) = crate::value::as_object(item) else {
        return item.clone();
    };
    LinoValue::Object(
        fields
            .iter()
            .filter_map(|field| {
                members
                    .iter()
                    .find(|(name, _)| name == field)
                    .map(|(name, value)| (name.clone(), value.clone()))
            })
            .collect(),
    )
}

/// Wrap items in the collection envelope of the specification.
///
/// # Examples
///
/// ```
/// use lino_rest_api::collection::collection_envelope;
/// use lino_rest_api::value::{get, int};
///
/// let envelope = collection_envelope(vec![int(1)], 20, 0, 1);
/// assert_eq!(get(get(&envelope, "page").unwrap(), "count"), Some(&int(1)));
/// ```
pub fn collection_envelope(
    items: Vec<LinoValue>,
    limit: usize,
    offset: usize,
    total: usize,
) -> LinoValue {
    let count = items.len();
    object([
        ("items", array(items)),
        (
            "page",
            object([
                ("limit", int(limit as i64)),
                ("offset", int(offset as i64)),
                ("total", int(total as i64)),
                ("count", int(count as i64)),
            ]),
        ),
    ])
}

/// Run a parsed collection query against an in-memory list.
pub fn apply_collection_query(items: &[LinoValue], query: &CollectionQuery) -> LinoValue {
    let filtered: Vec<LinoValue> = items
        .iter()
        .filter(|item| matches_filters(item, &query.filters))
        .cloned()
        .collect();
    let ordered = sort_items(&filtered, &query.sort);
    let page: Vec<LinoValue> = ordered
        .into_iter()
        .skip(query.offset)
        .take(query.limit)
        .map(|item| project_fields(&item, query.fields.as_ref()))
        .collect();

    collection_envelope(page, query.limit, query.offset, filtered.len())
}

/// Build the RFC 8288 `Link` header value for a paginated collection.
///
/// The value is empty when the page size is zero, because there is then nothing
/// to page through.
pub fn pagination_link_header(
    path: &str,
    query: &QueryParams,
    limit: usize,
    offset: usize,
    total: usize,
) -> String {
    if limit == 0 {
        return String::new();
    }

    let build = |target_offset: usize| {
        let mut parameters: Vec<String> = query
            .iter()
            .filter(|(name, _)| *name != "limit" && *name != "offset")
            .map(|(name, value)| format!("{}={}", form_encode(name), form_encode(value)))
            .collect();
        parameters.push(format!("limit={limit}"));
        parameters.push(format!("offset={target_offset}"));
        format!("{path}?{}", parameters.join("&"))
    };

    let last_offset = if total == 0 {
        0
    } else {
        ((total - 1) / limit) * limit
    };
    let mut links = vec![format!("<{}>; rel=\"first\"", build(0))];
    if offset > 0 {
        links.push(format!(
            "<{}>; rel=\"prev\"",
            build(offset.saturating_sub(limit))
        ));
    }
    if offset + limit < total {
        links.push(format!("<{}>; rel=\"next\"", build(offset + limit)));
    }
    links.push(format!("<{}>; rel=\"last\"", build(last_offset)));

    links.join(", ")
}
