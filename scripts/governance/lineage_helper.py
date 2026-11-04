from scripts.governance.datahub_client import DataHubClient

LINEAGE_QUERY = """
query GovernanceSearchAcrossLineage($input: SearchAcrossLineageInput!) {
    searchAcrossLineage(input: $input) {
        total
        searchResults {
            degree
            entity {
                urn
                type
            }
        }
    }
}
"""


def build_postgres_urn(model_name, settings):
    """Build the PostgreSQL dataset URN used as the lineage traversal root."""
    platform = settings.get("lineage_platform", "postgres")
    database = settings.get("database", "governance")
    schema = settings.get("schema", "analytics")
    environment = settings.get("environment", "PROD")

    return (
        f"urn:li:dataset:(urn:li:dataPlatform:{platform},"
        f"{database}.{schema}.{model_name},{environment})"
    )


def build_dbt_urn(model_name, settings):
    """Build the dbt URN used to identify the paired dbt entity."""
    database = settings.get("database", "governance")
    schema = settings.get("schema", "analytics")
    environment = settings.get("environment", "PROD")

    return (
        f"urn:li:dataset:(urn:li:dataPlatform:dbt,"
        f"{database}.{schema}.{model_name},{environment})"
    )


def get_direct_model_upstreams(client, model_name, settings):
    """
    Retrieve direct upstream PostgreSQL models by selecting
    the nearest PostgreSQL analytics datasets in the lineage graph.
    """
    input_data = {
        "urn": build_postgres_urn(model_name, settings),
        "query": "*",
        "start": 0,
        "count": int(settings.get("lineage_result_limit", 100)),
        "direction": "UPSTREAM",
    }

    data = client.execute(LINEAGE_QUERY, {"input": input_data})
    results = (data.get("searchAcrossLineage") or {}).get("searchResults") or []

    database = settings.get("database", "governance")
    schema = settings.get("schema", "analytics")
    platform = settings.get("lineage_platform", "postgres")

    prefix = f"urn:li:dataset:(urn:li:dataPlatform:{platform}," f"{database}.{schema}."

    candidates = []

    for result in results:
        entity = result.get("entity") or {}
        urn = entity.get("urn", "")
        degree = result.get("degree")

        if entity.get("type") != "DATASET":
            continue

        if not urn.startswith(prefix):
            continue

        if not isinstance(degree, int):
            continue

        upstream_name = urn[len(prefix) :].split(",", 1)[0]

        if upstream_name and upstream_name != model_name:
            candidates.append((upstream_name, degree))

    if not candidates:
        return set()

    minimum_degree = min(degree for _, degree in candidates)

    return {name for name, degree in candidates if degree == minimum_degree}


def build_actual_graph(client, rules):
    """Retrieve actual upstream dependencies for all governed models."""
    models = rules["models"]
    known_models = set(models)
    actual = {}

    for index, model in enumerate(sorted(models), start=1):
        print(f"  [{index}/{len(models)}] Reading lineage for {model}...")

        found = get_direct_model_upstreams(
            client,
            model,
            rules["settings"],
        )

        # Raw source tables are intentionally excluded.
        actual[model] = found & known_models

    return actual
