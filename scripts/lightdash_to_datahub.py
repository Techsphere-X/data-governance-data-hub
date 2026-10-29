"""Discover Lightdash dashboards and charts and publish them to DataHub."""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from datahub.sdk import Chart, Dashboard, DataHubClient
from datahub.metadata.urns import DatasetUrn

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

# Lightdash API fields that can identify a saved chart in a dashboard.
CHART_ID_KEYS = {
    "savedChartUuid",
    "savedChartUUID",
    "chartUuid",
    "chartUUID",
}


def load_env():
    if not ENV_FILE.is_file():
        raise FileNotFoundError(f"Missing configuration: {ENV_FILE}")

    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1]:
            if value[0] in ("'", '"'):
                value = value[1:-1]

        os.environ.setdefault(key.strip(), value)


def setting(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing {name} in {ENV_FILE}")
    return value


def get_json(url, token):
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"ApiKey {token}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def walk(obj):
    """Yield dictionaries nested anywhere in a JSON response."""
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk(value)


def find_dashboards(payload):
    found = {}
    for item in walk(payload):
        uuid = item.get("uuid")
        name = item.get("name")
        slug = item.get("slug")

        if isinstance(uuid, str) and name and slug and uuid not in found:
            found[uuid] = item

    return list(found.values())


def find_chart_ids(payload):
    found = []
    for item in walk(payload):
        for key in CHART_ID_KEYS:
            value = item.get(key)
            if isinstance(value, str) and value not in found:
                found.append(value)
    return found


def find_saved_chart(payload):
    for item in walk(payload):
        if "metricQuery" in item and item.get("name"):
            return item
    return None


def dataset_urn_for_model(model, platform):
    # These charts currently use models in the analytics schema.
    return DatasetUrn.from_string(
        f"urn:li:dataset:(urn:li:dataPlatform:{platform},"
        f"governance.analytics.{model},PROD)"
    )


def main():
    load_env()

    lightdash_url = setting("LIGHTDASH_URL").rstrip("/")
    token = setting("LIGHTDASH_API_KEY")
    project_uuid = setting("LIGHTDASH_PROJECT_UUID")
    datahub_url = setting("DATAHUB_URL").rstrip("/")
    platform = os.environ.get("DATAHUB_DATASET_PLATFORM", "postgres").strip()

    # Step 1: discover dashboards.
    print("Reading dashboards from Lightdash...")
    try:
        dashboard_payload = get_json(
            f"{lightdash_url}/api/v1/projects/" f"{project_uuid}/dashboards",
            token,
        )
    except Exception as exc:
        print(f"Could not retrieve dashboards: {exc}")
        return 1

    dashboards = find_dashboards(dashboard_payload)
    if not dashboards:
        print("No dashboards were recognized. Nothing was published.")
        return 1

    print(f"Found {len(dashboards)} dashboards.")

    # Step 2: retrieve all dashboard details and deduplicate saved charts.
    chart_to_dashboards = {}
    dashboard_details = {}

    for dashboard_info in dashboards:
        dashboard_id = dashboard_info["uuid"]

        try:
            details = get_json(
                f"{lightdash_url}/api/v2/projects/{project_uuid}"
                f"/dashboards/{dashboard_id}",
                token,
            )
        except Exception as exc:
            print(f"Could not retrieve dashboard " f"{dashboard_info['name']}: {exc}")
            return 1

        dashboard_details[dashboard_id] = (dashboard_info, details)

        chart_ids = find_chart_ids(details)
        print(f"  {dashboard_info['name']}: {len(chart_ids)} chart placements")

        for chart_id in chart_ids:
            chart_to_dashboards.setdefault(chart_id, set()).add(dashboard_id)

    print(f"\nFound {len(chart_to_dashboards)} unique saved chart IDs.")

    # Step 3: fetch every unique saved chart.
    charts_by_id = {}
    model_by_chart = {}

    for chart_id in chart_to_dashboards:
        try:
            payload = get_json(
                f"{lightdash_url}/api/v2/projects/{project_uuid}" f"/saved/{chart_id}",
                token,
            )
        except Exception as exc:
            print(f"Could not retrieve chart {chart_id}: {exc}")
            return 1

        saved_chart = find_saved_chart(payload)
        if not saved_chart:
            print(f"Could not parse chart metadata for {chart_id}.")
            return 1

        query = saved_chart.get("metricQuery") or {}
        table = saved_chart.get("tableName") or ""
        explore = query.get("exploreName") or ""
        model = table or explore

        if not model:
            print(
                f"Chart '{saved_chart.get('name')}' has no model/table "
                "identifier. Nothing was published."
            )
            return 1

        # Only synchronize models whose existing DataHub identity we can
        # construct and verify. Never create replacement datasets here.
        urn = dataset_urn_for_model(model, platform)

        charts_by_id[chart_id] = (saved_chart, urn)
        model_by_chart[chart_id] = model

        print(f"  Chart: {saved_chart.get('name')} " f"| model: {model}")

    # Step 4: verify every distinct dataset before publishing anything.
    client = DataHubClient(server=datahub_url)
    required_urns = {str(urn): urn for _, urn in charts_by_id.values()}
    existing_datasets = {}

    print("\nVerifying existing DataHub datasets...")
    for urn_text, urn in required_urns.items():
        try:
            dataset = client.entities.get(urn)
        except Exception as exc:
            print(f"Could not verify {urn_text}: {exc}")
            return 1

        if dataset is None:
            print(f"Dataset not found: {urn_text}")
            print(
                "Nothing was published. Check the platform, schema, "
                "dataset name and environment in DataHub."
            )
            return 1

        existing_datasets[urn_text] = dataset
        print(f"  Found: {urn_text}")

    # Step 5: prepare chart entities and dashboard-to-chart relationships.
    chart_entities = {}
    dashboard_entities = {}

    for chart_id, (saved_chart, dataset_urn) in charts_by_id.items():
        query = saved_chart.get("metricQuery") or {}
        metrics = query.get("metrics") or []
        model = model_by_chart[chart_id]

        chart = Chart(
            name=chart_id,
            platform="lightdash",
            display_name=saved_chart.get("name", chart_id),
            description=(
                f"Imported from Lightdash. Model: {model}. "
                f"Metrics: {', '.join(metrics)}."
            ),
            input_datasets=[dataset_urn],
            custom_properties={
                "lightdash_project_uuid": project_uuid,
                "lightdash_chart_uuid": chart_id,
                "lightdash_model": model,
                "lightdash_explore": str(query.get("exploreName", "")),
                "lightdash_metrics": ", ".join(metrics),
                "lightdash_slug": str(saved_chart.get("slug", "")),
            },
        )
        chart_entities[chart_id] = chart

    for dashboard_id, (info, details) in dashboard_details.items():
        associated_charts = [
            chart_entities[chart_id]
            for chart_id in chart_to_dashboards
            if dashboard_id in chart_to_dashboards[chart_id]
        ]

        dashboard = Dashboard(
            name=dashboard_id,
            platform="lightdash",
            display_name=info["name"],
            description="Imported from Lightdash.",
            charts=associated_charts,
            custom_properties={
                "lightdash_project_uuid": project_uuid,
                "lightdash_dashboard_uuid": dashboard_id,
                "lightdash_slug": info["slug"],
            },
        )
        dashboard_entities[dashboard_id] = dashboard

    # Step 6: show a summary and ask before making changes.
    print("\nSynchronization plan:")
    print(f"  Dashboards to upsert: {len(dashboard_entities)}")
    print(f"  Unique charts to upsert: {len(chart_entities)}")
    print(f"  Existing datasets to link: {len(existing_datasets)}")
    print("  Existing datasets will not be created or overwritten.")

    answer = input(
        "\nPublish these chart and dashboard entities to DataHub? "
        "Type YES to continue: "
    ).strip()

    if answer != "YES":
        print("Cancelled. No entities were submitted.")
        return 0

    # Upsert charts first, then dashboards that reference those charts.
    try:
        for chart in chart_entities.values():
            client.entities.upsert(chart)
        print(f"Submitted {len(chart_entities)} chart entities.")

        for dashboard in dashboard_entities.values():
            client.entities.upsert(dashboard)
        print(f"Submitted {len(dashboard_entities)} dashboard entities.")

    except Exception as exc:
        print(f"Publishing failed: {exc}")
        print(
            "Some entities may already have been submitted. "
            "Check DataHub before retrying."
        )
        return 1

    print("\nSynchronization requests completed.")
    print("Verify the dashboard/chart relationships and dataset lineage")
    print("in DataHub before treating the synchronization as complete.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, FileNotFoundError) as exc:
        print(f"Configuration error: {exc}")
        sys.exit(1)
