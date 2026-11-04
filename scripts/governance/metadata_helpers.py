from scripts.governance.datahub_client import DataHubClient

DATASET_QUERY = """
query GovernanceDatasetLookup($query: String!) {
    searchAcrossEntities(
        input: {
            query: $query
            types: [DATASET]
            start: 0
            count: 20
        }
    ) {
        searchResults {
            entity {
                urn
                ... on Dataset {
                    name
                    properties {
                        name
                        description
                    }
                    schemaMetadata {
                        fields {
                            fieldPath
                            description
                            tags {
                                tags {
                                    tag {
                                        urn
                                        name
                                    }
                                }
                            }
                        }
                    }
                    editableSchemaMetadata {
                        editableSchemaFieldInfo {
                            fieldPath
                            description
                            tags {
                                tags {
                                    tag {
                                        urn
                                        name
                                    }
                                }
                            }
                        }
                    }
                    globalTags {
                        tags {
                            tag {
                                urn
                                name
                            }
                        }
                    }
                    domain {
                        domain {
                            urn
                            properties {
                                name
                            }
                        }
                        associatedUrn
                    }
                }
            }
        }
    }
}
"""


def extract_tag_names(global_tags):
    """Extract tag names from a DataHub tag response."""
    if not global_tags:
        return set()

    return {
        item["tag"]["name"]
        for item in global_tags.get("tags", [])
        if item.get("tag") and item["tag"].get("name")
    }


def get_dataset_metadata(client, model_name):
    """
    Retrieve metadata from the dbt dataset only.

    PostgreSQL entities with the same model name are ignored.
    """

    data = client.execute(
        DATASET_QUERY,
        {"query": model_name},
    )

    results = data.get("searchAcrossEntities", {}).get("searchResults", [])

    dataset = None

    for result in results:
        entity = result.get("entity") or {}
        urn = entity.get("urn", "")

        properties = entity.get("properties") or {}
        entity_name = entity.get("name") or properties.get("name")

        if entity_name == model_name and "urn:li:dataPlatform:dbt" in urn:
            dataset = entity
            break

    if not dataset:
        raise LookupError(f"dbt dataset not found in DataHub: {model_name}")

    properties = dataset.get("properties") or {}

    # Model description
    model_description = properties.get("description")

    # Column descriptions from schemaMetadata
    column_descriptions = {}

    schema = dataset.get("schemaMetadata") or {}

    for field in schema.get("fields", []):
        field_path = field.get("fieldPath")

        if field_path:
            column_descriptions[field_path] = field.get("description")

    # Editable schema metadata is a fallback for descriptions.
    editable_schema = dataset.get("editableSchemaMetadata") or {}

    editable_fields = editable_schema.get("editableSchemaFieldInfo", [])

    for field in editable_fields:
        field_path = field.get("fieldPath")

        if field_path:
            editable_description = field.get("description")

            if not column_descriptions.get(field_path) and editable_description:
                column_descriptions[field_path] = editable_description

    # Model-level tags
    model_tags = extract_tag_names(dataset.get("globalTags"))

    # Column-level tags
    column_tags = {}

    for field in editable_fields:
        field_path = field.get("fieldPath")

        if field_path:
            column_tags[field_path] = extract_tag_names(field.get("tags"))

    for field in schema.get("fields", []):
        field_path = field.get("fieldPath")

        if field_path:
            existing_tags = column_tags.get(field_path, set())
            schema_tags = extract_tag_names(field.get("tags"))

            column_tags[field_path] = existing_tags | schema_tags

    # Domain
    domain_association = dataset.get("domain") or {}
    domain_object = domain_association.get("domain") or {}
    domain_properties = domain_object.get("properties") or {}

    return {
        "urn": dataset["urn"],
        "name": model_name,
        "description": model_description,
        "column_descriptions": column_descriptions,
        "tags": model_tags,
        "column_tags": column_tags,
        "domain": domain_properties.get("name"),
    }
