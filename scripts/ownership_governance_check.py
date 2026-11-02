#!/usr/bin/env python3

"""
DataHub Ownership Governance Audit

Checks:
1. Ownership completeness: each model has at least one owner.
2. Correct ownership type: assigned owners use expected types.
3. Correct ownership group: assigned owners belong to expected groups.
4. Ownership responsibility coverage: actual assignments match
   the expected ownership configuration.

Expected ownership rules are loaded from config/ownership_rules.yml.

The script reads ownership metadata from DataHub and publishes
custom assertion definitions and results back to DataHub through GraphQL.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

import yaml

# --------------------------------------------------
# 1. Project paths and environment configuration
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CONFIG_PATH = PROJECT_ROOT / "config" / "ownership_rules.yml"
ENV_PATH = PROJECT_ROOT / ".env"


def load_env_file(env_path):
    """
    Load environment variables from the project root .env file.

    Existing system environment variables take priority.
    No additional dotenv dependency is required.
    """

    if not env_path.exists():
        return

    with open(env_path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if line.startswith("export "):
                line = line[7:].strip()

            if "=" not in line:
                continue

            key, value = line.split("=", 1)

            key = key.strip()
            value = value.strip()

            # Remove surrounding quotes if present.
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]

            # Do not overwrite variables already provided by the environment.
            os.environ.setdefault(key, value)


load_env_file(ENV_PATH)


def get_required_env(name):
    """Retrieve a required environment variable."""

    value = os.getenv(name, "").strip()

    if not value:
        raise ValueError(
            f"Required environment variable '{name}' is missing. "
            f"Check the project root .env file."
        )

    return value


GMS_URL = get_required_env("DATAHUB_GMS_URL").rstrip("/")

GRAPHQL_URL = f"{GMS_URL}/api/graphql"

PLATFORM_NAME = get_required_env("GOVERNANCE_AUDIT_PLATFORM_NAME")

# DataHub platform identifier used to distinguish dbt datasets
# from PostgreSQL datasets.
DBT_PLATFORM_URN = "urn:li:dataPlatform:dbt"


# --------------------------------------------------
# 2. Load expected ownership configuration
# --------------------------------------------------


def load_expected_ownership():
    """Load expected ownership assignments from the YAML file."""

    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Ownership rules file not found: {CONFIG_PATH}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    models = config.get("models")

    if not isinstance(models, dict) or not models:
        raise ValueError(
            "ownership_rules.yml must contain a non-empty 'models' section."
        )

    expected_ownership = {}

    for model_name, assignments in models.items():

        if not isinstance(assignments, list) or not assignments:
            raise ValueError(
                f"Model '{model_name}' must have at least one ownership assignment."
            )

        expected_ownership[model_name] = []

        for assignment in assignments:

            if not isinstance(assignment, dict):
                raise ValueError(
                    f"Invalid ownership assignment for model '{model_name}'."
                )

            ownership_type = assignment.get("type")
            group = assignment.get("group")

            if not ownership_type or not group:
                raise ValueError(
                    f"Model '{model_name}' has an assignment missing type or group."
                )

            expected_ownership[model_name].append(
                (
                    str(ownership_type).strip(),
                    str(group).strip(),
                )
            )

    return expected_ownership


EXPECTED_OWNERSHIP = load_expected_ownership()


# --------------------------------------------------
# 3. GraphQL queries and mutations
# --------------------------------------------------

QUERY = """
query OwnershipAudit($modelName: String!) {
  searchAcrossEntities(
    input: {
      query: $modelName
      types: [DATASET]
      start: 0
      count: 50
    }
  ) {
    searchResults {
      entity {
        urn
        ... on Dataset {
          properties {
            name
          }
          ownership {
            owners {
              owner {
                ... on CorpGroup {
                  urn
                  properties {
                    displayName
                  }
                }
                ... on CorpUser {
                  urn
                  properties {
                    displayName
                  }
                }
              }
              ownershipType {
                urn
                type
                info {
                  name
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

UPSERT_ASSERTION_MUTATION = """
mutation UpsertOwnershipAssertion(
  $urn: String!,
  $input: UpsertCustomAssertionInput!
) {
  upsertCustomAssertion(urn: $urn, input: $input) {
    urn
  }
}
"""

REPORT_RESULT_MUTATION = """
mutation ReportOwnershipAssertionResult(
  $urn: String!,
  $result: AssertionResultInput!
) {
  reportAssertionResult(urn: $urn, result: $result)
}
"""


# --------------------------------------------------
# 4. GraphQL request helper
# --------------------------------------------------


def graphql_request(query, variables=None):

    payload = {
        "query": query,
        "variables": variables or {},
    }

    request = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DataHub HTTP {error.code}: {details}") from error

    except urllib.error.URLError as error:
        raise RuntimeError(f"Cannot connect to DataHub: {error.reason}") from error

    if result.get("errors"):
        raise RuntimeError(json.dumps(result["errors"], indent=2))

    return result.get("data") or {}


# --------------------------------------------------
# 5. Retrieve a dbt dataset from DataHub
# --------------------------------------------------


def get_dataset(model_name):

    data = graphql_request(
        QUERY,
        {"modelName": model_name},
    )

    search_results = data.get("searchAcrossEntities", {}).get("searchResults", [])

    for item in search_results:

        entity = item.get("entity") or {}
        urn = entity.get("urn", "")
        properties = entity.get("properties") or {}

        # Select the dbt dataset, not the PostgreSQL dataset.
        if properties.get("name") == model_name and DBT_PLATFORM_URN in urn:
            return entity

    return None


# --------------------------------------------------
# 6. Extract ownership assignments
# --------------------------------------------------


def get_owners(entity):

    ownership = entity.get("ownership") or {}
    owners = ownership.get("owners") or []

    assignments = []

    for item in owners:

        owner = item.get("owner") or {}
        properties = owner.get("properties") or {}

        owner_name = (
            properties.get("displayName") or owner.get("urn") or "Unknown owner"
        )

        ownership_type = item.get("ownershipType") or {}
        ownership_info = ownership_type.get("info") or {}

        type_name = (
            ownership_info.get("name")
            or ownership_type.get("type")
            or "Unknown ownership type"
        )

        assignments.append((type_name.strip(), owner_name.strip()))

    return assignments


# --------------------------------------------------
# 7. Evaluate separate governance rules
# --------------------------------------------------


def evaluate_rules(actual, expected):
    """
    Return a dictionary of individual rule results.

    Each result contains:
        passed: bool
        details: str
    """

    actual_set = set(actual)
    expected_set = set(expected)

    # Rule 1: At least one owner exists.
    completeness_passed = bool(actual)

    completeness_details = (
        f"Found {len(actual)} ownership assignment(s)."
        if completeness_passed
        else "No owner is assigned."
    )

    # Rule 2: Ownership types match the expected configuration.
    expected_types = {ownership_type for ownership_type, _ in expected}

    actual_types = {ownership_type for ownership_type, _ in actual}

    unexpected_types = actual_types - expected_types

    type_passed = bool(actual) and not unexpected_types

    type_details = (
        "Ownership types are valid."
        if type_passed
        else (
            "Unexpected ownership type(s): " + ", ".join(sorted(unexpected_types))
            if unexpected_types
            else "Cannot validate ownership type because no owner is assigned."
        )
    )

    # Rule 3: Ownership groups match the expected configuration.
    expected_groups = {group for _, group in expected}

    actual_groups = {group for _, group in actual}

    unexpected_groups = actual_groups - expected_groups

    group_passed = bool(actual) and not unexpected_groups

    group_details = (
        "Ownership groups are valid."
        if group_passed
        else (
            "Unexpected ownership group(s): " + ", ".join(sorted(unexpected_groups))
            if unexpected_groups
            else "Cannot validate ownership group because no owner is assigned."
        )
    )

    # Rule 4: The complete set of type/group pairs matches exactly.
    missing = expected_set - actual_set
    unexpected = actual_set - expected_set

    consistency_passed = not missing and not unexpected

    consistency_messages = []

    for ownership_type, group in sorted(missing):
        consistency_messages.append(f"Missing {group} ({ownership_type})")

    for ownership_type, group in sorted(unexpected):
        consistency_messages.append(f"Unexpected {group} ({ownership_type})")

    consistency_details = (
        "Actual assignments match the expected configuration."
        if consistency_passed
        else "; ".join(consistency_messages)
    )

    return {
        "ownership_completeness": {
            "passed": completeness_passed,
            "details": completeness_details,
        },
        "correct_ownership_type": {
            "passed": type_passed,
            "details": type_details,
        },
        "correct_ownership_group": {
            "passed": group_passed,
            "details": group_details,
        },
        "ownership_responsibility_coverage": {
            "passed": consistency_passed,
            "details": consistency_details,
        },
    }


# --------------------------------------------------
# 8. Register an assertion and publish its result
# --------------------------------------------------

RULE_DESCRIPTIONS = {
    "ownership_completeness": (
        "Ownership completeness",
        "Every governed dbt model must have at least one owner assigned.",
    ),
    "correct_ownership_type": (
        "Correct ownership type",
        "Ownership assignments must use the expected ownership type.",
    ),
    "correct_ownership_group": (
        "Correct ownership group",
        "Ownership assignments must use the expected ownership group.",
    ),
    "ownership_responsibility_coverage": (
        "Ownership responsibility coverage",
        "Actual ownership type/group assignments must match the expected "
        "governance configuration.",
    ),
}


def make_assertion_urn(model_name, rule_key):
    """Stable assertion URN, reused across script executions."""

    return f"urn:li:assertion:ownership_{model_name}_{rule_key}"


def publish_assertion_result(
    dataset_urn,
    model_name,
    rule_key,
    rule_result,
):

    assertion_urn = make_assertion_urn(
        model_name,
        rule_key,
    )

    rule_title, rule_description = RULE_DESCRIPTIONS[rule_key]

    passed = rule_result["passed"]
    details = rule_result["details"]

    full_description = f"{rule_title} for {model_name}. {rule_description}"

    # Register/update the custom assertion.
    graphql_request(
        UPSERT_ASSERTION_MUTATION,
        {
            "urn": assertion_urn,
            "input": {
                "entityUrn": dataset_urn,
                "type": "CUSTOM",
                "description": full_description,
                "platform": {
                    "name": PLATFORM_NAME,
                },
                "logic": (
                    f"Python ownership governance audit: {rule_title}. "
                    "The result is computed from the current DataHub "
                    "ownership metadata and expected ownership rules."
                ),
            },
        },
    )

    result_type = "SUCCESS" if passed else "FAILURE"

    # Report the actual result of this evaluation.
    graphql_request(
        REPORT_RESULT_MUTATION,
        {
            "urn": assertion_urn,
            "result": {
                "timestampMillis": int(time.time() * 1000),
                "type": result_type,
                "properties": [
                    {"key": "model", "value": model_name},
                    {"key": "rule", "value": rule_title},
                    {
                        "key": "checked_by",
                        "value": Path(__file__).name,
                    },
                    {
                        "key": "status",
                        "value": "PASS" if passed else "FAIL",
                    },
                    {"key": "details", "value": details},
                ],
            },
        },
    )

    return assertion_urn


# --------------------------------------------------
# 9. Main audit
# --------------------------------------------------


def main():

    print("\n========================================")
    print(" DATAHUB OWNERSHIP GOVERNANCE AUDIT")
    print("========================================")

    models = EXPECTED_OWNERSHIP

    print(f"\nRules loaded from: {CONFIG_PATH}")
    print(f"Models to check: {len(models)}")
    print(f"DataHub GMS: {GMS_URL}")
    print(f"Assertion platform: {PLATFORM_NAME}")
    print("Publishing assertion results to DataHub: enabled\n")

    passed_models = []
    failed_models = []
    publishing_errors = []

    for model_name, expected in models.items():

        print(f"\n--- {model_name} ---")

        try:

            dataset = get_dataset(model_name)

            if dataset is None:
                print("FAIL | dbt dataset not found")
                failed_models.append(model_name)
                continue

            actual = get_owners(dataset)

            rule_results = evaluate_rules(
                actual,
                expected,
            )

            model_passed = all(result["passed"] for result in rule_results.values())

            for rule_key, result in rule_results.items():

                status = "PASS" if result["passed"] else "FAIL"

                print(
                    f"{status} | "
                    f"{RULE_DESCRIPTIONS[rule_key][0]} "
                    f"| {result['details']}"
                )

                try:

                    assertion_urn = publish_assertion_result(
                        dataset_urn=dataset["urn"],
                        model_name=model_name,
                        rule_key=rule_key,
                        rule_result=result,
                    )

                    print(f"       Published: {assertion_urn}")

                except RuntimeError as error:

                    message = f"{model_name}/{rule_key}: {error}"

                    publishing_errors.append(message)

                    print(f"       PUBLISH ERROR: {error}")

            if model_passed:
                passed_models.append(model_name)
            else:
                failed_models.append(model_name)

        except RuntimeError as error:

            print(f"ERROR | {error}")
            failed_models.append(model_name)

    # --------------------------------------------------
    # 10. Summary
    # --------------------------------------------------

    print("\n========================================")
    print(" AUDIT SUMMARY")
    print("========================================")

    print(f"Models checked: {len(models)}")
    print(f"Passed: {len(passed_models)}")
    print(f"Failed: {len(failed_models)}")
    print(f"Assertion publishing errors: {len(publishing_errors)}")

    if publishing_errors:
        print("\nPublishing errors:")

        for error in publishing_errors:
            print(f"- {error}")

    if failed_models or publishing_errors:

        print("\nOwnership governance audit FAILED.")
        sys.exit(1)

    print("\nAll checked models match the expected ownership rules.")
    print("Ownership governance audit PASSED.")

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError) as error:
        print(f"\nCONFIGURATION ERROR: {error}")
        sys.exit(1)
