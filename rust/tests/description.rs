//! The service description, ported from `python/tests/test_description.py`
//! (specification section 9).

use lino_objects_codec::LinoValue;
use lino_rest_api::description::{
    LINO_API_DESCRIPTION_VERSION, ServiceInfo, info_object, openapi_document, path_parameters,
    service_description, to_openapi_path,
};
use lino_rest_api::media_type::LINO_CONTENT_TYPE;
use lino_rest_api::router::RouteDescription;
use lino_rest_api::value::{as_array, as_object, get, has, string};

/// The member of a value, which every test below expects to be there.
fn member<'a>(value: &'a LinoValue, key: &str) -> &'a LinoValue {
    get(value, key).unwrap_or_else(|| panic!("value has no member {key}"))
}

/// Follow a path of member names.
fn at<'a>(value: &'a LinoValue, path: &[&str]) -> &'a LinoValue {
    path.iter().fold(value, |current, key| member(current, key))
}

/// The service the tests describe.
fn info() -> ServiceInfo {
    ServiceInfo::new("Items API", "1.0.0")
}

/// The routes the tests describe.
fn routes() -> Vec<RouteDescription> {
    vec![
        RouteDescription {
            path: "/items".to_string(),
            methods: vec!["GET".to_string(), "POST".to_string()],
            summary: Some("Item collection".to_string()),
        },
        RouteDescription {
            path: "/items/:id".to_string(),
            methods: vec!["GET".to_string(), "DELETE".to_string()],
            summary: None,
        },
    ]
}

/// Whether an array of strings contains one.
fn contains(value: &LinoValue, expected: &str) -> bool {
    as_array(value)
        .map(|items| items.contains(&string(expected)))
        .unwrap_or(false)
}

#[test]
fn the_description_lists_the_version_the_info_and_the_media_types() {
    let description = service_description(&info(), &routes(), None);
    assert_eq!(
        member(&description, "lino_api"),
        &string(LINO_API_DESCRIPTION_VERSION)
    );
    assert_eq!(member(&description, "info"), &info_object(&info()));
    assert!(contains(
        member(&description, "media_types"),
        LINO_CONTENT_TYPE
    ));

    let described = as_array(member(&description, "routes")).expect("routes is an array");
    assert_eq!(described.len(), 2);
    assert_eq!(member(&described[0], "path"), &string("/items"));
    assert!(contains(member(&described[0], "methods"), "POST"));
    assert_eq!(member(&described[0], "summary"), &string("Item collection"));
    assert!(!has(&described[1], "summary"));
}

#[test]
fn path_parameters_are_translated_to_the_openapi_template_syntax() {
    assert_eq!(
        to_openapi_path("/items/:id/tags/:tag"),
        "/items/{id}/tags/{tag}"
    );
    assert_eq!(
        path_parameters("/items/:id/tags/:tag"),
        vec!["id".to_string(), "tag".to_string()]
    );
}

#[test]
fn the_openapi_document_declares_every_representation() {
    let document = openapi_document(&info(), &routes(), None);
    assert_eq!(member(&document, "openapi"), &string("3.1.0"));
    let operation = at(&document, &["paths", "/items", "get"]);
    assert!(has(
        at(operation, &["responses", "200", "content"]),
        LINO_CONTENT_TYPE
    ));
    assert_eq!(member(operation, "summary"), &string("Item collection"));
}

#[test]
fn bodies_are_declared_for_methods_that_carry_one() {
    let document = openapi_document(&info(), &routes(), None);
    assert!(has(
        at(&document, &["paths", "/items", "post"]),
        "requestBody"
    ));
    assert!(!has(
        at(&document, &["paths", "/items", "get"]),
        "requestBody"
    ));
}

#[test]
fn path_parameters_appear_in_the_operation() {
    let document = openapi_document(&info(), &routes(), None);
    let parameters = as_array(at(
        &document,
        &["paths", "/items/{id}", "get", "parameters"],
    ))
    .expect("parameters is an array");
    let names: Vec<&LinoValue> = parameters
        .iter()
        .map(|parameter| member(parameter, "name"))
        .collect();
    assert_eq!(names, vec![&string("id")]);
}

#[test]
fn every_operation_declares_a_default_problem_response() {
    let document = openapi_document(&info(), &routes(), None);
    let paths = as_object(member(&document, "paths")).expect("paths is an object");
    for (_, path) in paths {
        let operations = as_object(path).expect("a path is an object");
        for (_, operation) in operations {
            assert!(has(member(operation, "responses"), "default"));
        }
    }
}

#[test]
fn a_prose_description_is_carried_by_both_documents() {
    let mut described = info();
    described.description = Some("A task list".to_string());
    assert_eq!(
        at(
            &service_description(&described, &routes(), None),
            &["info", "description"]
        ),
        &string("A task list")
    );
    assert_eq!(
        at(
            &openapi_document(&described, &routes(), None),
            &["info", "description"]
        ),
        &string("A task list")
    );
}

#[test]
fn the_info_object_omits_an_absent_description() {
    assert!(!has(&info_object(&info()), "description"));
    let mut empty = info();
    empty.description = Some(String::new());
    assert!(!has(&info_object(&empty), "description"));
}

#[test]
fn the_media_types_of_a_description_can_be_narrowed() {
    let only_lino = vec![LINO_CONTENT_TYPE.to_string()];
    let description = service_description(&info(), &routes(), Some(&only_lino));
    assert_eq!(
        as_array(member(&description, "media_types")),
        Some(&vec![string(LINO_CONTENT_TYPE)])
    );
    let document = openapi_document(&info(), &routes(), Some(&only_lino));
    let content = at(
        &document,
        &["paths", "/items", "get", "responses", "200", "content"],
    );
    assert_eq!(as_object(content).map(Vec::len), Some(1));
}
