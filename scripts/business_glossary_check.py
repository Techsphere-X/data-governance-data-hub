#!/usr/bin/env python3

"""
DataHub business glossary governance checker with optional assertion publishing.

Checks:
- Glossary term validity
- Model-level glossary coverage
- Model-level business term relevance
- Column-level glossary relevance
- Required column glossary assignments
- Irrelevant glossary assignments
- Consistent column glossary usage
- Glossary definition completeness

By default, the checker is read-only. Use --publish to publish rule
definitions and their latest results as DataHub custom assertions.
"""

import argparse
import sys
from pathlib import Path
from collections import defaultdict

import yaml

from scripts.governance.datahub_client import DataHubClient
from scripts.governance.assertion_publisher import AssertionPublisher
from scripts.governance.business_glossary_helpers import (
    get_dataset_glossary_metadata,
    get_glossary_catalog,
)

# --------------------------------------------------
# 1. Paths and configuration
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RULES_FILE = (
    Path(__file__).resolve().parents[1] / "config" / "business_glossary_rules.yml"
)


# --------------------------------------------------
# 2. Load rules
# --------------------------------------------------


def load_rules():
    if not RULES_FILE.exists():
        raise FileNotFoundError(f"Glossary rules file not found: {RULES_FILE}")

    with RULES_FILE.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    if not config.get("models"):
        raise ValueError("No models are configured in business_glossary_rules.yml")

    return config


# --------------------------------------------------
# 3. Small helper functions
# --------------------------------------------------


def get_term_names(term_dictionary):
    return set(term_dictionary.keys())


def format_terms(terms):
    if not terms:
        return "none"

    return ", ".join(sorted(terms))


def get_required_terms(model_config):
    return set(model_config.get("required_terms") or [])


def get_required_column_terms(column_config):
    return set(column_config.get("required_terms") or [])


def get_forbidden_column_terms(column_config):
    return set(column_config.get("forbidden_terms") or [])


def add_result(results, rule_name, passed, details=""):
    results[rule_name] = {
        "status": "PASS" if passed else "FAIL",
        "details": details,
    }


# --------------------------------------------------
# 4. Rule evaluation
# --------------------------------------------------


def evaluate_model(model_name, model_config, metadata, catalog):
    results = {}

    actual_model_terms = get_term_names(metadata["model_terms"])

    required_model_terms = get_required_terms(model_config)

    configured_columns = model_config.get("columns") or {}

    actual_column_terms = metadata["column_terms"]

    column_metadata_available = metadata["column_metadata_available"]

    catalog_names = set(catalog.keys())

    # ----------------------------------------------
    # Rule 1: Glossary term validity
    # ----------------------------------------------

    assigned_terms = set(actual_model_terms)

    if column_metadata_available:
        for terms in actual_column_terms.values():
            assigned_terms.update(get_term_names(terms))

    invalid_terms = assigned_terms - catalog_names

    add_result(
        results,
        "glossary_term_validity",
        not invalid_terms,
        (
            "All assigned terms exist in the glossary catalog."
            if not invalid_terms
            else f"Unknown terms: {format_terms(invalid_terms)}"
        ),
    )

    # ----------------------------------------------
    # Rule 2: Model glossary coverage
    # ----------------------------------------------

    missing_model_terms = required_model_terms - actual_model_terms

    add_result(
        results,
        "model_glossary_coverage",
        not missing_model_terms,
        (
            "Required model terms are assigned."
            if not missing_model_terms
            else ("Missing model terms: " f"{format_terms(missing_model_terms)}")
        ),
    )

    # ----------------------------------------------
    # Rule 3: Business term relevance
    # ----------------------------------------------

    unexpected_model_terms = actual_model_terms - required_model_terms

    add_result(
        results,
        "business_term_relevance",
        not unexpected_model_terms,
        (
            "Model-level terms match the approved model terms."
            if not unexpected_model_terms
            else ("Unexpected model terms: " f"{format_terms(unexpected_model_terms)}")
        ),
    )

    # ----------------------------------------------
    # Rule 4: Column glossary relevance
    # ----------------------------------------------

    if not column_metadata_available:
        add_result(
            results,
            "column_glossary_relevance",
            False,
            "Cannot verify column glossary assignments: editable column metadata unavailable.",
        )
    else:
        irrelevant_columns = []

        for column_name, column_config in configured_columns.items():
            expected = get_required_column_terms(column_config)

            forbidden = get_forbidden_column_terms(column_config)

            actual = get_term_names(actual_column_terms.get(column_name, {}))

            unexpected = actual - expected
            forbidden_found = actual & forbidden

            if unexpected or forbidden_found:
                reasons = []

                if unexpected:
                    reasons.append(f"unexpected: {format_terms(unexpected)}")

                if forbidden_found:
                    reasons.append(f"forbidden: {format_terms(forbidden_found)}")

                irrelevant_columns.append(f"{column_name} ({'; '.join(reasons)})")

        add_result(
            results,
            "column_glossary_relevance",
            not irrelevant_columns,
            (
                "Configured column terms are relevant."
                if not irrelevant_columns
                else ("Incorrect column terms: " + ", ".join(irrelevant_columns))
            ),
        )

    # ----------------------------------------------
    # Rule 5: Required glossary assignment
    # ----------------------------------------------

    if not column_metadata_available:
        add_result(
            results,
            "required_glossary_assignment",
            False,
            "Cannot verify column glossary assignments: editable column metadata unavailable.",
        )
    else:
        missing_assignments = []

        for column_name, column_config in configured_columns.items():
            required = get_required_column_terms(column_config)

            actual = get_term_names(actual_column_terms.get(column_name, {}))

            missing = required - actual

            if missing:
                missing_assignments.append(f"{column_name}: {format_terms(missing)}")

        add_result(
            results,
            "required_glossary_assignment",
            not missing_assignments,
            (
                "All required column terms are assigned."
                if not missing_assignments
                else ("Missing column assignments: " + "; ".join(missing_assignments))
            ),
        )

    # ----------------------------------------------
    # Rule 6: No irrelevant glossary terms
    # ----------------------------------------------

    irrelevant_items = []

    if unexpected_model_terms:
        irrelevant_items.append("model: " + format_terms(unexpected_model_terms))

    if column_metadata_available:
        for column_name, column_config in configured_columns.items():
            expected = get_required_column_terms(column_config)

            forbidden = get_forbidden_column_terms(column_config)

            actual = get_term_names(actual_column_terms.get(column_name, {}))

            unexpected = actual - expected
            forbidden_found = actual & forbidden

            if unexpected or forbidden_found:
                terms_to_report = unexpected | forbidden_found

                irrelevant_items.append(
                    f"{column_name}: {format_terms(terms_to_report)}"
                )

    add_result(
        results,
        "no_irrelevant_glossary_terms",
        not irrelevant_items,
        (
            "No irrelevant glossary assignments found."
            if not irrelevant_items
            else "; ".join(irrelevant_items)
        ),
    )

    # ----------------------------------------------
    # Rule 7: Consistent glossary usage
    # ----------------------------------------------

    if not column_metadata_available:
        add_result(
            results,
            "consistent_glossary_usage",
            False,
            "Cannot verify column glossary assignments: editable column metadata unavailable.",
        )
    else:
        inconsistent_columns = []

        for column_name, column_config in configured_columns.items():
            expected = get_required_column_terms(column_config)

            actual = get_term_names(actual_column_terms.get(column_name, {}))

            if actual != expected:
                inconsistent_columns.append(
                    (
                        f"{column_name} "
                        f"(expected: {format_terms(expected)}; "
                        f"actual: {format_terms(actual)})"
                    )
                )

        add_result(
            results,
            "consistent_glossary_usage",
            not inconsistent_columns,
            (
                "Configured columns use their exact expected terms."
                if not inconsistent_columns
                else ("Inconsistent assignments: " + "; ".join(inconsistent_columns))
            ),
        )

    return results


# --------------------------------------------------
# 5. Glossary definition completeness
# --------------------------------------------------


def check_glossary_definitions(config, catalog):
    required_terms = set()

    for model_config in config["models"].values():
        required_terms.update(get_required_terms(model_config))

        for column_config in (model_config.get("columns") or {}).values():
            required_terms.update(get_required_column_terms(column_config))

    missing_terms = required_terms - set(catalog.keys())

    terms_without_definitions = []

    for term_name in required_terms & set(catalog.keys()):
        description = (catalog[term_name].get("description") or "").strip()

        if not description:
            terms_without_definitions.append(term_name)

    problems = []

    if missing_terms:
        problems.append("Terms not found in catalog: " + format_terms(missing_terms))

    if terms_without_definitions:
        problems.append(
            "Terms without descriptions: "
            + format_terms(set(terms_without_definitions))
        )

    passed = not problems

    return {
        "status": "PASS" if passed else "FAIL",
        "details": (
            "All required glossary terms have definitions."
            if passed
            else "; ".join(problems)
        ),
    }


# --------------------------------------------------
# 6. Main checker
# --------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Validate DataHub business glossary governance rules."
    )

    publish_group = parser.add_mutually_exclusive_group()

    publish_group.add_argument(
        "--publish",
        action="store_true",
        help="Publish/update custom assertions and their latest results in DataHub.",
    )

    publish_group.add_argument(
        "--no-publish",
        action="store_true",
        help="Run checks without publishing assertions (default).",
    )

    args = parser.parse_args()

    should_publish = args.publish

    try:
        config = load_rules()

        client = DataHubClient()

        publisher = AssertionPublisher(client) if should_publish else None

        models = config["models"]

        enabled_checks = config.get("checks") or {}

        catalog = get_glossary_catalog(client)

    except Exception as error:
        print(f"ERROR: {error}")
        return 2

    print("\nDATAHUB BUSINESS GLOSSARY CHECK")
    print("-" * 42)

    print(f"Models configured: {len(models)}")

    passed_models = []
    failed_models = []
    model_results = {}

    rule_totals = defaultdict(lambda: {"PASS": 0, "FAIL": 0})

    assertion_passed = 0
    assertion_failed = 0

    publish_errors = []
    publish_count = 0
    publish_target_urn = None

    if should_publish:
        print("Assertion publishing: ENABLED")
    else:
        print("Assertion publishing: DISABLED (use --publish to enable)")

    # ----------------------------------------------
    # Check each configured model
    # ----------------------------------------------

    for model_name, model_config in models.items():

        try:
            metadata = get_dataset_glossary_metadata(
                client,
                model_name,
            )

            results = evaluate_model(
                model_name,
                model_config,
                metadata,
                catalog,
            )

            entity_urn = metadata.get("urn")

            if entity_urn and publish_target_urn is None:
                publish_target_urn = entity_urn

        except Exception as error:
            failed_models.append(model_name)

            model_results[model_name] = {}

            print(f"FAIL | {model_name} | {error}")

            continue

        model_failed = False

        for rule_name, result in results.items():

            if not enabled_checks.get(rule_name, False):
                continue

            status = result["status"]

            rule_totals[rule_name][status] += 1

            if status == "PASS":
                assertion_passed += 1

            elif status == "FAIL":
                assertion_failed += 1

                model_failed = True

            # --------------------------------------
            # Publish model-level assertion
            # --------------------------------------

            if should_publish:

                entity_urn = metadata.get("urn")

                if not entity_urn:
                    publish_errors.append(
                        f"{model_name}/{rule_name}: dataset URN missing from metadata"
                    )

                else:
                    try:
                        publisher.publish(
                            entity_urn=entity_urn,
                            model_name=model_name,
                            rule_key=rule_name,
                            description=(
                                f"Business glossary governance rule: {rule_name}. "
                                f"Latest checker detail: {result['details']}"
                            ),
                            passed=(status == "PASS"),
                        )

                        publish_count += 1

                    except Exception as publish_error:
                        publish_errors.append(
                            f"{model_name}/{rule_name}: {publish_error}"
                        )

        model_results[model_name] = results

        if model_failed:
            failed_models.append(model_name)

        else:
            passed_models.append(model_name)

    # ----------------------------------------------
    # Global glossary definition check
    # ----------------------------------------------

    definition_result = check_glossary_definitions(
        config,
        catalog,
    )

    if enabled_checks.get(
        "glossary_definition_completeness",
        False,
    ):

        definition_status = definition_result["status"]

        rule_totals["glossary_definition_completeness"][definition_status] += 1

        if definition_status == "PASS":
            assertion_passed += 1

        else:
            assertion_failed += 1

        # This is one global check, so publish it once and associate it with
        # the first dataset whose metadata was successfully retrieved.

        if should_publish:

            if not publish_target_urn:
                publish_errors.append(
                    "glossary_definition_completeness: no dataset URN available "
                    "for the global assertion"
                )

            else:
                try:
                    publisher.publish(
                        entity_urn=publish_target_urn,
                        model_name="global_glossary",
                        rule_key="glossary_definition_completeness",
                        description=(
                            "Global business glossary definition completeness check. "
                            f"Latest checker detail: {definition_result['details']}"
                        ),
                        passed=(definition_status == "PASS"),
                    )

                    publish_count += 1

                except Exception as publish_error:
                    publish_errors.append(
                        f"global_glossary/glossary_definition_completeness: {publish_error}"
                    )

    # ----------------------------------------------
    # Final report
    # ----------------------------------------------

    print("\nSUMMARY")
    print("-" * 42)

    print(
        f"Models: {len(models)} | "
        f"Passed: {len(passed_models)} | "
        f"Failed: {len(failed_models)}"
    )

    print(f"Assertions: {assertion_passed} passed | " f"{assertion_failed} failed")

    print("\nRULE RESULTS")

    for rule_name, counts in rule_totals.items():

        print(f"{rule_name}: " f"{counts['PASS']} passed, " f"{counts['FAIL']} failed")

    # ----------------------------------------------
    # Show only failed models and their reasons
    # ----------------------------------------------

    if failed_models:

        print("\nFAILED MODELS")

        for model_name in failed_models:

            print(f"\n{model_name}")

            results = model_results.get(model_name, {})

            for rule_name, result in results.items():

                if result["status"] == "FAIL":

                    print(f"  FAIL | {rule_name} | " f"{result['details']}")

            if not results:
                print("  Dataset could not be checked.")

        if definition_result["status"] == "FAIL":

            print("\nGlossary definitions: " + definition_result["details"])

    elif definition_result["status"] == "FAIL":

        print("\nGlossary definitions: " + definition_result["details"])

    else:

        print("\nAll enabled glossary checks passed.")

    # ----------------------------------------------
    # Publishing report
    # ----------------------------------------------

    if should_publish:

        print("\nASSERTION PUBLISHING SUMMARY")

        print(f"Assertions published/updated: {publish_count}")

    if publish_errors:

        print("\nASSERTION PUBLISHING ERRORS")

        for error in publish_errors:

            print(f"  ERROR | {error}")

    print("-" * 42)

    if publish_errors:
        return 2

    return 1 if failed_models or assertion_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
