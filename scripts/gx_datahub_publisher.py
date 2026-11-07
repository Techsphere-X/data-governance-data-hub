import json
import os
import re

from scripts.governance.assertion_publisher import AssertionPublisher

# Checkpoint-to-dbt-model mapping
CHECKPOINT_MODELS = {
    "delivered_orders_checkpoint": "fact_orders",
    "fact_orders_checkpoint": "fact_orders",
    "fact_orders_business_checkpoint": "fact_orders",
    "dim_customers_checkpoint": "dim_customers",
    "fact_supplier_shipments_checkpoint": "fact_supplier_shipments",
}


def get_dataset_urn(model_name):
    """Build the existing dbt dataset URN."""

    platform = os.getenv("DATAHUB_GX_PLATFORM", "dbt")
    database = os.getenv("DATAHUB_GX_DATABASE", "governance")
    schema = os.getenv("DATAHUB_GX_SCHEMA", "analytics")
    environment = os.getenv("DATAHUB_GX_ENV", "PROD")

    return (
        f"urn:li:dataset:(urn:li:dataPlatform:{platform},"
        f"{database}.{schema}.{model_name},{environment})"
    )


def get_value(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)

    return getattr(obj, key, default)


def extract_expectations(checkpoint_result):
    """Extract expectation results from a GX checkpoint."""

    run_results = get_value(checkpoint_result, "run_results", {}) or {}
    extracted = []

    for run_result in run_results.values():

        # GX may return the validation result directly.
        validation = get_value(
            run_result,
            "validation_result",
            run_result,
        )

        results = get_value(validation, "results", []) or []

        for item in results:

            config = get_value(item, "expectation_config", {}) or {}
            kwargs = get_value(config, "kwargs", {}) or {}
            details = get_value(item, "result", {}) or {}

            extracted.append(
                {
                    "type": get_value(
                        config,
                        "expectation_type",
                        "unknown_expectation",
                    ),
                    "column": kwargs.get("column", "table"),
                    "kwargs": kwargs,
                    "passed": bool(get_value(item, "success", False)),
                    "details": details,
                }
            )

    return extracted


def publish_gx_results(validation_results):

    print("\nPUBLISHING GX RESULTS TO DATAHUB")
    print("-" * 40)

    publisher = AssertionPublisher()

    published = 0
    errors = 0

    for checkpoint_name, checkpoint_result in validation_results.items():

        model_name = CHECKPOINT_MODELS.get(checkpoint_name)

        if not model_name:
            print(f"Unknown checkpoint: {checkpoint_name}")
            errors += 1
            continue

        entity_urn = get_dataset_urn(model_name)

        expectations = extract_expectations(checkpoint_result)

        if not expectations:
            print(f"No expectation results: {checkpoint_name}")
            errors += 1
            continue

        for item in expectations:

            expectation_type = item["type"]
            column = item["column"]

            rule_key = re.sub(
                r"[^a-zA-Z0-9_]",
                "_",
                f"gx_{checkpoint_name}_{expectation_type}_{column}",
            ).lower()

            details = item["details"]

            description = (
                "Great Expectations data quality check.\n"
                f"Checkpoint: {checkpoint_name}\n"
                f"Expectation: {expectation_type}\n"
                f"Column: {column}\n"
                f"Result: {'PASSED' if item['passed'] else 'FAILED'}\n"
                f"Rows evaluated: {get_value(details, 'element_count', 'N/A')}\n"
                f"Unexpected rows: {get_value(details, 'unexpected_count', 'N/A')}\n"
                f"Parameters: {json.dumps(item['kwargs'], default=str)}"
            )

            try:
                publisher.publish(
                    entity_urn=entity_urn,
                    model_name=model_name,
                    rule_key=rule_key,
                    description=description,
                    passed=item["passed"],
                )

                published += 1

            except Exception as error:
                errors += 1
                print(f"Failed: {model_name} / {column}: {error}")

    print(f"Assertions published: {published}")
    print(f"Publishing errors: {errors}")

    return {
        "published": published,
        "errors": errors,
    }
