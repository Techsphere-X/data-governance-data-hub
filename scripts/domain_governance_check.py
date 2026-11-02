from pathlib import Path
import yaml

from scripts.governance.datahub_client import DataHubClient
from scripts.governance.metadata_helpers import get_dataset_metadata
from scripts.governance.assertion_publisher import AssertionPublisher

ROOT = Path(__file__).resolve().parents[1]
RULES_FILE = ROOT / "config" / "domain_rules.yml"


def main():

    with open(RULES_FILE, encoding="utf-8") as file:
        config = yaml.safe_load(file)

    client = DataHubClient()
    publisher = AssertionPublisher(client)

    passed_count = 0
    failed_count = 0

    for model_name, expected_domain in config["models"].items():

        metadata = get_dataset_metadata(client, model_name)

        actual_domain = metadata["domain"]

        # Normalize domain names to avoid whitespace mismatches
        expected_domain = (expected_domain or "").strip()
        actual_domain = (actual_domain or "").strip()

        domain_passed = expected_domain == actual_domain

        print(f"\nModel: {model_name}")
        print(f"Expected domain: {expected_domain}")
        print(f"Actual domain: {actual_domain}")
        print(f"Result: {'PASS' if domain_passed else 'FAIL'}")

        if not domain_passed:
            print("  Domain assignment mismatch!")

        publisher.publish(
            metadata["urn"],
            model_name,
            "domain_assignment",
            "Check expected domain assignment",
            domain_passed,
        )

        passed_count += int(domain_passed)
        failed_count += int(not domain_passed)

    print("\n========== DOMAIN AUDIT ==========")
    print(f"Passed: {passed_count}")
    print(f"Failed: {failed_count}")
    print(f"Total:  {passed_count + failed_count}")
    print("==================================")


if __name__ == "__main__":
    main()
