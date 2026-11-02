from pathlib import Path

import yaml

from scripts.governance.datahub_client import DataHubClient
from scripts.governance.metadata_helpers import get_dataset_metadata
from scripts.governance.assertion_publisher import AssertionPublisher

ROOT = Path(__file__).resolve().parents[1]
RULES_FILE = ROOT / "config" / "classification_rules.yml"


def normalize_tags(tags):
    """Normalize tag names to avoid capitalization mismatches."""
    return {tag.strip().casefold() for tag in tags if tag}


def main():
    with open(RULES_FILE, encoding="utf-8") as file:
        config = yaml.safe_load(file)

    client = DataHubClient()
    publisher = AssertionPublisher(client)

    passed_count = 0
    failed_count = 0

    for model_name, expected in config["models"].items():
        metadata = get_dataset_metadata(client, model_name)

        print(f"\n{'=' * 60}")
        print(f"Checking model: {model_name}")
        print("=" * 60)

        # --------------------------------------------------
        # 1. Model-level tag check
        # --------------------------------------------------
        expected_model_tags = set(expected.get("tags", []))
        actual_model_tags = metadata["tags"]

        missing_model_tags = normalize_tags(expected_model_tags) - normalize_tags(
            actual_model_tags
        )

        model_passed = not missing_model_tags

        print("\nModel-level tags")
        print(f"  Expected: {sorted(expected_model_tags)}")
        print(f"  Actual:   {sorted(actual_model_tags)}")
        print(f"  Result:   {'PASS' if model_passed else 'FAIL'}")

        if missing_model_tags:
            print(f"  Missing:  {sorted(missing_model_tags)}")

        publisher.publish(
            metadata["urn"],
            model_name,
            "model_tags",
            "Check expected model-level classification tags",
            model_passed,
        )

        passed_count += int(model_passed)
        failed_count += int(not model_passed)

        # --------------------------------------------------
        # 2. Column-level tag checks
        # --------------------------------------------------
        expected_columns = expected.get("columns", {})
        actual_column_tags = metadata.get("column_tags", {})

        for column_name, expected_tags in expected_columns.items():
            # An empty columns dictionary means no column rules
            # are configured for this model.
            expected_tags = set(expected_tags)
            actual_tags = actual_column_tags.get(column_name, set())

            missing_tags = normalize_tags(expected_tags) - normalize_tags(actual_tags)

            column_passed = not missing_tags

            print(f"\nColumn: {column_name}")
            print(f"  Expected: {sorted(expected_tags)}")
            print(f"  Actual:   {sorted(actual_tags)}")
            print(f"  Result:   {'PASS' if column_passed else 'FAIL'}")

            if missing_tags:
                print(f"  Missing:  {sorted(missing_tags)}")

            publisher.publish(
                metadata["urn"],
                model_name,
                f"column_tags_{column_name}",
                f"Check expected classification tags for column {column_name}",
                column_passed,
            )

            passed_count += int(column_passed)
            failed_count += int(not column_passed)

    print("\n========== CLASSIFICATION AUDIT ==========")
    print(f"Passed: {passed_count}")
    print(f"Failed: {failed_count}")
    print(f"Total:  {passed_count + failed_count}")
    print("===========================================")


if __name__ == "__main__":
    main()
