"""Tests for the service description (specification section 9)."""

from lino_rest_api.description import (
    LINO_API_DESCRIPTION_VERSION,
    info_object,
    openapi_document,
    path_parameters,
    service_description,
    to_openapi_path,
)
from lino_rest_api.media_type import LINO_CONTENT_TYPE

INFO = {"title": "Items API", "version": "1.0.0"}
ROUTES = [
    {"path": "/items", "methods": ["GET", "POST"], "summary": "Item collection"},
    {"path": "/items/:id", "methods": ["GET", "DELETE"]},
]


def test_the_description_lists_the_version_the_info_and_the_media_types():
    description = service_description(INFO, ROUTES)
    assert description["lino_api"] == LINO_API_DESCRIPTION_VERSION
    assert description["info"] == INFO
    assert LINO_CONTENT_TYPE in description["media_types"]
    assert description["routes"] == ROUTES


def test_path_parameters_are_translated_to_the_openapi_template_syntax():
    assert to_openapi_path("/items/:id/tags/:tag") == "/items/{id}/tags/{tag}"
    assert path_parameters("/items/:id/tags/:tag") == ["id", "tag"]


def test_the_openapi_document_declares_every_representation():
    document = openapi_document(INFO, ROUTES)
    assert document["openapi"] == "3.1.0"
    operation = document["paths"]["/items"]["get"]
    assert LINO_CONTENT_TYPE in operation["responses"]["200"]["content"]
    assert operation["summary"] == "Item collection"


def test_bodies_are_declared_for_methods_that_carry_one():
    document = openapi_document(INFO, ROUTES)
    assert document["paths"]["/items"]["post"]["requestBody"]
    assert "requestBody" not in document["paths"]["/items"]["get"]


def test_path_parameters_appear_in_the_operation():
    document = openapi_document(INFO, ROUTES)
    parameters = document["paths"]["/items/{id}"]["get"]["parameters"]
    assert [parameter["name"] for parameter in parameters] == ["id"]


def test_every_operation_declares_a_default_problem_response():
    document = openapi_document(INFO, ROUTES)
    for path in document["paths"].values():
        for operation in path.values():
            assert operation["responses"]["default"]


def test_a_prose_description_is_carried_by_both_documents():
    info = {**INFO, "description": "A task list"}
    assert service_description(info, ROUTES)["info"]["description"] == "A task list"
    assert openapi_document(info, ROUTES)["info"]["description"] == "A task list"


def test_the_info_object_omits_an_absent_description():
    assert info_object(INFO) == INFO
    assert "description" not in info_object({**INFO, "description": ""})
