import argparse
import json
from collections import defaultdict
from pathlib import Path

import yaml

from scripts.governance.datahub_client import DataHubClient
from scripts.governance.assertion_publisher import AssertionPublisher
from scripts.governance.lineage_helper import build_actual_graph

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RULES_FILE = PROJECT_ROOT / "config" / "lineage_rules.yml"


RULE_INFO = {
    "LIN-01": {
        "title": "Upstream completeness",
        "description": (
            "Checks that every model has all expected upstream dependencies "
            "defined in the governance rules."
        ),
    },
    "LIN-02": {
        "title": "Downstream completeness",
        "description": (
            "Checks that every model has all expected downstream relationships."
        ),
    },
    "LIN-03": {
        "title": "Unexpected dependencies",
        "description": (
            "Checks that models do not have additional upstream dependencies "
            "outside the expected lineage."
        ),
    },
    "LIN-04": {
        "title": "Lineage continuity",
        "description": (
            "Checks that every mart model can trace its lineage back "
            "to at least one staging model."
        ),
    },
    "LIN-05": {
        "title": "Layer connectivity",
        "description": (
            "Checks that dependencies follow the correct direction: "
            "staging -> intermediate -> mart."
        ),
    },
}


def load_rules():
    with open(RULES_FILE, "r", encoding="utf-8") as file:
        rules = yaml.safe_load(file)

    required = {"settings", "checks", "models"}
    missing = required - set(rules or {})

    if missing:
        raise ValueError(f"Missing sections in lineage rules: {sorted(missing)}")

    for model, config in rules["models"].items():
        if config.get("layer") not in {
            "staging",
            "intermediate",
            "mart",
        }:
            raise ValueError(f"{model}: invalid or missing layer")

        for upstream in config.get("upstream", []):
            if upstream not in rules["models"]:
                raise ValueError(f"{model}: unknown upstream model '{upstream}'")

    return rules


def reverse_graph(graph, model_names):
    downstream = defaultdict(set)

    for model, upstreams in graph.items():
        for upstream in upstreams:
            downstream[upstream].add(model)

    return {model: set(downstream.get(model, set())) for model in model_names}


def get_ancestors(model, graph):
    visited = set()
    stack = list(graph.get(model, set()))

    while stack:
        current = stack.pop()

        if current not in visited:
            visited.add(current)
            stack.extend(graph.get(current, set()) - visited)

    return visited


def add_result(results, rule_id, model, passed, details):
    results.append(
        {
            "rule_id": rule_id,
            "model": model,
            "status": "PASS" if passed else "FAIL",
            "details": details,
        }
    )


def run_checks(rules, actual):
    models = rules["models"]
    names = set(models)

    expected = {
        model: set(config.get("upstream", [])) for model, config in models.items()
    }

    results = []
    checks = rules["checks"]

    # LIN-01: Upstream completeness
    if checks.get("upstream_completeness"):
        for model in sorted(names):
            missing = expected[model] - actual[model]

            add_result(
                results,
                "LIN-01",
                model,
                not missing,
                {
                    "expected": sorted(expected[model]),
                    "actual": sorted(actual[model]),
                    "missing": sorted(missing),
                },
            )

    # LIN-02: Downstream completeness
    if checks.get("downstream_completeness"):
        expected_down = reverse_graph(expected, names)
        actual_down = reverse_graph(actual, names)

        for model in sorted(names):
            missing = expected_down[model] - actual_down[model]

            add_result(
                results,
                "LIN-02",
                model,
                not missing,
                {
                    "expected": sorted(expected_down[model]),
                    "actual": sorted(actual_down[model]),
                    "missing": sorted(missing),
                },
            )

    # LIN-03: Unexpected dependencies
    if checks.get("unexpected_dependencies"):
        for model in sorted(names):
            unexpected = actual[model] - expected[model]

            add_result(
                results,
                "LIN-03",
                model,
                not unexpected,
                {
                    "expected": sorted(expected[model]),
                    "actual": sorted(actual[model]),
                    "unexpected": sorted(unexpected),
                },
            )

    # LIN-04: Lineage continuity
    if checks.get("lineage_continuity"):
        staging = {
            name for name, config in models.items() if config["layer"] == "staging"
        }

        for model, config in sorted(models.items()):
            if config["layer"] == "mart":
                reachable = get_ancestors(model, actual) & staging

                add_result(
                    results,
                    "LIN-04",
                    model,
                    bool(reachable),
                    {
                        "reachable_staging": sorted(reachable),
                        "message": (
                            "Staging lineage is reachable"
                            if reachable
                            else "No staging lineage is reachable"
                        ),
                    },
                )

    # LIN-05: Layer connectivity
    if checks.get("layer_connectivity"):
        order = {
            "staging": 0,
            "intermediate": 1,
            "mart": 2,
        }

        for downstream, upstreams in sorted(expected.items()):
            invalid = [
                {
                    "upstream": upstream,
                    "upstream_layer": models[upstream]["layer"],
                    "downstream": downstream,
                    "downstream_layer": models[downstream]["layer"],
                }
                for upstream in sorted(upstreams)
                if order[models[upstream]["layer"]] > order[models[downstream]["layer"]]
            ]

            add_result(
                results,
                "LIN-05",
                downstream,
                not invalid,
                {
                    "checked_upstream_edges": len(upstreams),
                    "invalid_edges": invalid,
                },
            )

    return results


def print_rule_results(results):
    grouped = defaultdict(list)

    for result in results:
        grouped[result["rule_id"]].append(result)

    for rule_id in RULE_INFO:
        rule_results = grouped.get(rule_id, [])

        if not rule_results:
            continue

        info = RULE_INFO[rule_id]

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

                if rule_id == "LIN-01":
                    print("    Missing upstream dependencies: " f"{details['missing']}")
                    print(f"    Expected: {details['expected']}")
                    print(f"    Actual:   {details['actual']}")

                elif rule_id == "LIN-02":
                    print(
                        "    Missing downstream dependencies: " f"{details['missing']}"
                    )
                    print(f"    Expected: {details['expected']}")
                    print(f"    Actual:   {details['actual']}")

                elif rule_id == "LIN-03":
                    print(
                        "    Unexpected upstream dependencies: "
                        f"{details['unexpected']}"
                    )
                    print(f"    Expected: {details['expected']}")
                    print(f"    Actual:   {details['actual']}")

                elif rule_id == "LIN-04":
                    print("    Reason: No staging model is reachable.")

                elif rule_id == "LIN-05":
                    print("    Invalid layer dependencies:")

                    for edge in details["invalid_edges"]:
                        print(
                            f"      {edge['upstream']} "
                            f"({edge['upstream_layer']}) -> "
                            f"{edge['downstream']} "
                            f"({edge['downstream_layer']})"
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
            f"{result['rule_id']} lineage governance check for {model}. "
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
        description="Run DataHub lineage governance checks."
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
    print("              DATAHUB LINEAGE GOVERNANCE CHECK")
    print("=" * 75)
    print(f"Models configured: {len(rules['models'])}")
    print("\nRetrieving actual lineage from DataHub...")

    actual = build_actual_graph(client, rules)
    results = run_checks(rules, actual)

    # Display results grouped by governance rule.
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
                print(f"  {error['rule_id']} | " f"{error['model']} | {error['error']}")

    print("\n")
    print("=" * 75)
    print("                  FINAL GOVERNANCE SUMMARY")
    print("=" * 75)
    print(f"Total assertions : {len(results)}")
    print(f"Passed           : {passed}")
    print(f"Failed           : {failed}")
    print(f"Overall status   : {overall_status}")

    if args.no_publish:
        print("DataHub publishing: Skipped (--no-publish)")
    else:
        print(f"DataHub publishing: {published} assertions")

    print("=" * 75)


if __name__ == "__main__":
    main()
