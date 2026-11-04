import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import yaml

from scripts.governance.datahub_client import DataHubClient
from scripts.governance.assertion_publisher import AssertionPublisher
from scripts.governance.metadata_helpers import get_dataset_metadata

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RULES_FILE = PROJECT_ROOT / "config" / "metadata_rules.yml"


RULE_INFO = {
    "MET-01": {
        "title": "Model description completeness",
        "description": (
            "Checks that every dbt model has a non-empty description " "in DataHub."
        ),
    },
    "MET-02": {
        "title": "Column description completeness",
        "description": (
            "Checks that every column in every dbt model has a "
            "non-empty description in DataHub."
        ),
    },
    "MET-03": {
        "title": "Model naming convention",
        "description": (
            "Checks that model names use the correct layer prefix "
            "and lowercase snake_case format."
        ),
    },
}


LAYER_PREFIXES = {
    "staging": "stg_",
    "intermediate": "int_",
    "mart": ("dim_", "fact_"),
}


def load_rules():
    with open(RULES_FILE, "r", encoding="utf-8") as file:
        rules = yaml.safe_load(file)

    required = {"settings", "checks", "naming", "models"}
    missing = required - set(rules or {})

    if missing:
        raise ValueError(f"Missing sections in metadata rules: {sorted(missing)}")

    if not rules["models"]:
        raise ValueError("No models configured in metadata_rules.yml")

    for model, config in rules["models"].items():
        if config.get("layer") not in LAYER_PREFIXES:
            raise ValueError(f"{model}: invalid or missing layer")

    return rules


def add_result(results, rule_id, model, passed, details):
    results.append(
        {
            "rule_id": rule_id,
            "model": model,
            "status": "PASS" if passed else "FAIL",
            "details": details,
        }
    )


def retrieve_all_metadata(client, rules):
    """Retrieve metadata for all configured dbt models."""

    metadata = {}

    model_names = sorted(rules["models"])

    print("\nRetrieving dbt metadata from DataHub...")

    for index, model in enumerate(model_names, start=1):
        print(f"  [{index}/{len(model_names)}] Reading {model}...")

        metadata[model] = get_dataset_metadata(client, model)

        print(
            f"       Platform: dbt"
            f" | Columns: {len(metadata[model]['column_descriptions'])}"
        )

    return metadata


def check_model_description(model, metadata, results):
    description = metadata.get("description")

    passed = bool(isinstance(description, str) and description.strip())

    add_result(
        results,
        "MET-01",
        model,
        passed,
        {
            "description_present": passed,
            "description": description,
        },
    )


def check_column_descriptions(model, metadata, results):
    columns = metadata.get("column_descriptions") or {}

    missing_columns = [
        column
        for column, description in columns.items()
        if not isinstance(description, str) or not description.strip()
    ]

    column_count = len(columns)

    passed = column_count > 0 and len(missing_columns) == 0

    add_result(
        results,
        "MET-02",
        model,
        passed,
        {
            "total_columns": column_count,
            "described_columns": column_count - len(missing_columns),
            "missing_columns": sorted(missing_columns),
            "reason": (
                "No columns found in DataHub schema metadata."
                if column_count == 0
                else None
            ),
        },
    )


def check_model_naming(model, layer, pattern, results):
    matches_pattern = bool(re.fullmatch(pattern, model))

    expected_prefix = LAYER_PREFIXES[layer]

    if isinstance(expected_prefix, tuple):
        correct_prefix = model.startswith(expected_prefix)
        expected_prefix_display = " or ".join(expected_prefix)
    else:
        correct_prefix = model.startswith(expected_prefix)
        expected_prefix_display = expected_prefix

    passed = matches_pattern and correct_prefix

    add_result(
        results,
        "MET-03",
        model,
        passed,
        {
            "model_name": model,
            "expected_layer": layer,
            "expected_prefix": expected_prefix_display,
            "matches_snake_case": matches_pattern,
            "correct_layer_prefix": correct_prefix,
        },
    )


def run_checks(rules, metadata):
    results = []

    checks = rules["checks"]
    naming_pattern = rules["naming"]["pattern"]

    for model, config in sorted(rules["models"].items()):
        model_metadata = metadata[model]

        if checks.get("model_description_completeness"):
            check_model_description(
                model,
                model_metadata,
                results,
            )

        if checks.get("column_description_completeness"):
            check_column_descriptions(
                model,
                model_metadata,
                results,
            )

        if checks.get("model_naming_convention"):
            check_model_naming(
                model,
                config["layer"],
                naming_pattern,
                results,
            )

    return results


def print_rule_results(results):
    grouped = defaultdict(list)

    for result in results:
        grouped[result["rule_id"]].append(result)

    for rule_id, info in RULE_INFO.items():
        rule_results = grouped.get(rule_id, [])

        if not rule_results:
            continue

        passed = sum(result["status"] == "PASS" for result in rule_results)

        failed = len(rule_results) - passed

        print("\n")
        print("=" * 75)
        print(f"{rule_id} | {info['title'].upper()}")
        print("-" * 75)
        print(f"RULE: {info['description']}")
        print("-" * 75)

        print(
            f"RESULT: {passed} PASSED | {failed} FAILED "
            f"| {len(rule_results)} CHECKED"
        )

        failures = [result for result in rule_results if result["status"] == "FAIL"]

        successes = [result for result in rule_results if result["status"] == "PASS"]

        if failures:
            print("\nFAILED MODELS:")

            for result in failures:
                model = result["model"]
                details = result["details"]

                print(f"\n  [FAIL] {model}")

                if rule_id == "MET-01":
                    print("    Model description is missing or empty.")

                elif rule_id == "MET-02":
                    print(f"    Total columns: {details['total_columns']}")
                    print(f"    Missing descriptions: " f"{details['missing_columns']}")

                    if details["reason"]:
                        print(f"    Reason: {details['reason']}")

                elif rule_id == "MET-03":
                    print(f"    Expected layer: {details['expected_layer']}")
                    print(f"    Expected prefix: {details['expected_prefix']}")
                    print(f"    Snake_case valid: " f"{details['matches_snake_case']}")
                    print(
                        f"    Layer prefix valid: " f"{details['correct_layer_prefix']}"
                    )

        else:
            print("\nNo failed models.")

        if successes:
            print("\nPASSED MODELS:")

            model_names = [result["model"] for result in successes]

            for index in range(0, len(model_names), 3):
                print("  " + " | ".join(model_names[index : index + 3]))


def publish_assertions(results, settings, client):
    publisher = AssertionPublisher(client=client)

    published = 0
    errors = []

    for result in results:
        model = result["model"]

        entity_urn = (
            "urn:li:dataset:(urn:li:dataPlatform:dbt,"
            f"{settings.get('database', 'governance')}."
            f"{settings.get('schema', 'analytics')}.{model},"
            f"{settings.get('environment', 'PROD')})"
        )

        description = (
            f"{result['rule_id']} metadata governance check "
            f"for {model}. "
            f"Status: {result['status']}. "
            f"Details: {json.dumps(result['details'], sort_keys=True)}"
        )

        try:
            publisher.publish(
                entity_urn=entity_urn,
                model_name=model,
                rule_key=result["rule_id"],
                description=description,
                passed=result["status"] == "PASS",
            )

            published += 1

        except Exception as exc:
            errors.append(
                {
                    "model": model,
                    "rule_id": result["rule_id"],
                    "error": str(exc),
                }
            )

    return published, errors


def main():
    parser = argparse.ArgumentParser(
        description="Run DataHub metadata governance checks."
    )

    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="Run checks without publishing DataHub assertions.",
    )

    args = parser.parse_args()

    rules = load_rules()
    client = DataHubClient()

    print("\n" + "=" * 75)
    print("              DATAHUB METADATA GOVERNANCE CHECK")
    print("=" * 75)

    print(f"Models configured: {len(rules['models'])}")
    print("Platform filter: dbt only")
    print("PostgreSQL entities: ignored")

    metadata = retrieve_all_metadata(client, rules)

    results = run_checks(rules, metadata)

    print_rule_results(results)

    passed = sum(result["status"] == "PASS" for result in results)

    failed = len(results) - passed

    overall_status = "PASS" if failed == 0 else "FAIL"

    published = 0
    errors = []

    if not args.no_publish:
        print("\n" + "=" * 75)
        print("PUBLISHING ASSERTIONS TO DATAHUB")
        print("=" * 75)

        published, errors = publish_assertions(
            results,
            rules["settings"],
            client,
        )

        print(f"Assertions published: {published}")

        if errors:
            print(f"\nPublishing errors: {len(errors)}")

            for error in errors:
                print(
                    f"  {error['rule_id']} | "
                    f"{error['model']} | "
                    f"{error['error']}"
                )

    print("\n")
    print("=" * 75)
    print("                FINAL GOVERNANCE SUMMARY")
    print("=" * 75)

    print(f"Models checked   : {len(rules['models'])}")
    print(f"Total assertions : {len(results)}")
    print(f"Passed           : {passed}")
    print(f"Failed           : {failed}")
    print(f"Overall status   : {overall_status}")

    if args.no_publish:
        print("DataHub publishing: Skipped (--no-publish)")
    else:
        print(f"DataHub publishing: {published} assertions")

        if errors:
            print(f"Publishing errors: {len(errors)}")

    print("=" * 75)


if __name__ == "__main__":
    main()
