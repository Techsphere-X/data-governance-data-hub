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
                    properties {
                        name
                    }
                    globalTags {
                        tags {
                            tag {
                                urn
                                name
                            }
                        }
                    }
                    schemaMetadata {
                        fields {
                            fieldPath
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
    """Retrieve model-level tags, column-level tags, and domain."""
    data = client.execute(DATASET_QUERY, {"query": model_name})

    results = data.get("searchAcrossEntities", {}).get("searchResults", [])

    dataset = None

    for result in results:
        entity = result.get("entity") or {}
        properties = entity.get("properties") or {}

        if properties.get(
            "name"
        ) == model_name and "urn:li:dataPlatform:dbt" in entity.get("urn", ""):
            dataset = entity
            break

    if not dataset:
        raise LookupError(f"dbt dataset not found: {model_name}")

    # Model-level tags
    model_tags = extract_tag_names(dataset.get("globalTags"))

    # Column-level tags:
    # DataHub UI-edited column tags are stored in editableSchemaMetadata.
    column_tags = {}

    editable_schema = dataset.get("editableSchemaMetadata") or {}
    editable_fields = editable_schema.get("editableSchemaFieldInfo") or []

    for field in editable_fields:
        field_path = field.get("fieldPath")

        if field_path:
            column_tags[field_path] = extract_tag_names(field.get("tags"))

    # Also read schemaMetadata tags as a fallback.
    # Merge them with editable tags if the same column appears in both.
    schema = dataset.get("schemaMetadata") or {}

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
        "tags": model_tags,
        "column_tags": column_tags,
        "domain": domain_properties.get("name"),
    }
