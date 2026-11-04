"""
Business glossary metadata helpers for DataHub.

Model-level terms:
    Dataset.glossaryTerms

Column-level assignments:
    Dataset.editableSchemaMetadata.editableSchemaFieldInfo

Only dbt datasets are accepted. PostgreSQL duplicates are ignored.
"""

from scripts.governance.datahub_client import DataHubClient

DATASET_GLOSSARY_QUERY = """
query BusinessGlossaryDatasetLookup($query: String!) {
    searchAcrossEntities(
        input: {
            query: $query
            types: [DATASET]
            start: 0
            count: 30
        }
    ) {
        searchResults {
            entity {
                urn
                ... on Dataset {
                    name
                    glossaryTerms {
                        terms {
                            term {
                                urn
                                glossaryTermInfo {
                                    name
                                    description
                                }
                            }
                        }
                    }
                    editableSchemaMetadata {
                        editableSchemaFieldInfo {
                            fieldPath
                            glossaryTerms {
                                terms {
                                    term {
                                        urn
                                        glossaryTermInfo {
                                            name
                                            description
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
"""


GLOSSARY_TERMS_QUERY = """
query BusinessGlossaryTermsLookup($query: String!) {
    searchAcrossEntities(
        input: {
            query: $query
            types: [GLOSSARY_TERM]
            start: 0
            count: 100
        }
    ) {
        searchResults {
            entity {
                urn
                ... on GlossaryTerm {
                    glossaryTermInfo {
                        name
                        description
                    }
                }
            }
        }
    }
}
"""


def extract_glossary_terms(glossary_data):
    """Return assigned glossary terms as a dictionary keyed by term name."""

    if not glossary_data:
        return {}

    terms = {}

    for item in glossary_data.get("terms") or []:
        term = item.get("term") or {}
        info = term.get("glossaryTermInfo") or {}

        name = info.get("name")

        if name:
            terms[name] = {
                "urn": term.get("urn"),
                "name": name,
                "description": info.get("description"),
            }

    return terms


def get_dataset_glossary_metadata(client, model_name):
    """
    Retrieve glossary metadata for one dbt model.

    Returns:
        urn
        name
        model_terms
        column_terms
        column_metadata_available
    """

    data = client.execute(
        DATASET_GLOSSARY_QUERY,
        {"query": model_name},
    )

    results = data.get("searchAcrossEntities", {}).get("searchResults", [])

    dataset = None

    for result in results:
        entity = result.get("entity") or {}
        urn = entity.get("urn", "")

        if entity.get("name") == model_name and "urn:li:dataPlatform:dbt" in urn:
            dataset = entity
            break

    if not dataset:
        raise LookupError(f"dbt dataset not found in DataHub: {model_name}")

    # Model-level assignments.
    model_terms = extract_glossary_terms(dataset.get("glossaryTerms"))

    # Column-level assignments must come from editable metadata.
    editable_schema = dataset.get("editableSchemaMetadata")

    column_metadata_available = editable_schema is not None
    column_terms = {}

    if column_metadata_available:
        fields = editable_schema.get("editableSchemaFieldInfo") or []

        for field in fields:
            field_path = field.get("fieldPath")

            if not field_path:
                continue

            column_terms[field_path] = extract_glossary_terms(
                field.get("glossaryTerms")
            )

    return {
        "urn": dataset["urn"],
        "name": model_name,
        "model_terms": model_terms,
        "column_terms": column_terms,
        "column_metadata_available": column_metadata_available,
    }


def get_glossary_catalog(client):
    """
    Retrieve available glossary terms from DataHub.

    The checker uses this catalog to validate term names and definitions.
    """

    data = client.execute(
        GLOSSARY_TERMS_QUERY,
        {"query": "*"},
    )

    results = data.get("searchAcrossEntities", {}).get("searchResults", [])

    catalog = {}

    for result in results:
        entity = result.get("entity") or {}
        info = entity.get("glossaryTermInfo") or {}

        name = info.get("name")

        if name:
            catalog[name] = {
                "urn": entity.get("urn"),
                "name": name,
                "description": info.get("description"),
            }

    return catalog
