import os
import sys
import great_expectations as gx

# ==================================================
# 1. PROJECT IMPORTS
# ==================================================

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.gx_datahub_publisher import publish_gx_results

# ==================================================
# 2. LOAD GX PROJECT AND CONNECTION
# ==================================================

context = gx.get_context(
    mode="file",
    project_root_dir="./gx_project",
)

connection_string = os.environ.get("POSTGRES_CONNECTION_STRING")

if not connection_string:
    raise EnvironmentError("POSTGRES_CONNECTION_STRING is not set.")


# ==================================================
# 3. POSTGRESQL DATA SOURCE
# ==================================================

datasource_name = "olist_postgres"

try:
    data_source = context.data_sources.get(datasource_name)
    print("Reusing PostgreSQL data source.")

except LookupError:
    data_source = context.data_sources.add_postgres(
        name=datasource_name,
        connection_string=connection_string,
    )
    print("Created PostgreSQL data source.")


# ==================================================
# 4. HELPER: GET OR CREATE ASSET AND BATCH
# ==================================================


def get_or_create_asset_and_batch(asset_name, query, batch_name):

    try:
        asset = data_source.get_asset(asset_name)

    except LookupError:
        asset = data_source.add_query_asset(
            name=asset_name,
            query=query,
        )

    try:
        batch = asset.get_batch_definition(batch_name)

    except LookupError:
        batch = asset.add_batch_definition_whole_table(
            name=batch_name,
        )

    return batch


# ==================================================
# 5. DEFINE QUERIES AND BATCHES
# ==================================================

delivered_batch = get_or_create_asset_and_batch(
    "delivered_orders",
    """
        SELECT order_id, order_delivered_customer_at
        FROM analytics.fact_orders
        WHERE order_status = 'delivered'
    """,
    "all_delivered_orders",
)

fact_orders_batch = get_or_create_asset_and_batch(
    "fact_orders_all",
    """
        SELECT order_id, total_order_value
        FROM analytics.fact_orders
    """,
    "all_fact_orders",
)

fact_orders_business_batch = get_or_create_asset_and_batch(
    "fact_orders_business_rules",
    """
        SELECT
            order_id,
            order_status,
            CASE
                WHEN order_delivered_customer_at >= order_purchase_at
                THEN TRUE
                ELSE FALSE
            END AS delivery_date_valid
        FROM analytics.fact_orders
        WHERE order_delivered_customer_at IS NOT NULL
    """,
    "all_fact_orders_business_rules",
)

customers_batch = get_or_create_asset_and_batch(
    "dim_customers_quality",
    """
        SELECT customer_id
        FROM analytics.dim_customers
    """,
    "all_dim_customers",
)

shipments_batch = get_or_create_asset_and_batch(
    "supplier_shipments_quality",
    """
        SELECT shipment_id, shipment_status, actual_delivery_date
        FROM analytics.fact_supplier_shipments
        WHERE shipment_status = 'Delivered'
    """,
    "all_delivered_shipments",
)


# ==================================================
# 6. HELPER: CREATE OR UPDATE EXPECTATION SUITES
# ==================================================


def get_or_create_suite(suite_name, expectations):

    try:
        suite = context.suites.get(name=suite_name)

    except gx.exceptions.DataContextError:
        suite = gx.ExpectationSuite(name=suite_name)

    added_count = 0

    for expectation in expectations:

        if expectation not in suite.expectations:
            suite.add_expectation(expectation)
            added_count += 1

    if added_count > 0:
        context.suites.add_or_update(suite)

    return suite


# ==================================================
# 7. EXPECTATION SUITES
# ==================================================

delivered_suite = get_or_create_suite(
    "delivered_orders_quality",
    [
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="order_delivered_customer_at"
        ),
    ],
)

fact_suite = get_or_create_suite(
    "fact_orders_quality",
    [
        gx.expectations.ExpectColumnValuesToNotBeNull(column="order_id"),
        gx.expectations.ExpectColumnValuesToBeUnique(column="order_id"),
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="total_order_value",
            min_value=0,
        ),
    ],
)

approved_order_statuses = [
    "approved",
    "canceled",
    "delivered",
    "invoiced",
    "processing",
    "shipped",
    "unavailable",
]

fact_business_suite = get_or_create_suite(
    "fact_orders_business_quality",
    [
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="delivery_date_valid",
            value_set=[True],
        ),
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="order_status",
            value_set=approved_order_statuses,
        ),
    ],
)

customers_suite = get_or_create_suite(
    "dim_customers_quality",
    [
        gx.expectations.ExpectColumnValuesToNotBeNull(column="customer_id"),
    ],
)

shipments_suite = get_or_create_suite(
    "fact_supplier_shipments_quality",
    [
        gx.expectations.ExpectColumnValuesToNotBeNull(column="actual_delivery_date"),
    ],
)


# ==================================================
# 8. VALIDATION DEFINITIONS
# ==================================================


def get_or_create_validation(validation_name, batch, suite):

    try:
        return context.validation_definitions.get(name=validation_name)

    except gx.exceptions.DataContextError:
        validation = gx.ValidationDefinition(
            name=validation_name,
            data=batch,
            suite=suite,
        )

        context.validation_definitions.add(validation)

        return validation


validations = [
    get_or_create_validation(
        "delivered_orders_validation",
        delivered_batch,
        delivered_suite,
    ),
    get_or_create_validation(
        "fact_orders_validation",
        fact_orders_batch,
        fact_suite,
    ),
    get_or_create_validation(
        "fact_orders_business_validation",
        fact_orders_business_batch,
        fact_business_suite,
    ),
    get_or_create_validation(
        "dim_customers_validation",
        customers_batch,
        customers_suite,
    ),
    get_or_create_validation(
        "fact_supplier_shipments_validation",
        shipments_batch,
        shipments_suite,
    ),
]


# ==================================================
# 9. DATA DOCS REPORT SITE
# ==================================================

site_name = "local_site"

site_config = {
    "class_name": "SiteBuilder",
    "site_index_builder": {
        "class_name": "DefaultSiteIndexBuilder",
    },
    "store_backend": {
        "class_name": "TupleFilesystemStoreBackend",
        "base_directory": "uncommitted/data_docs/local_site/",
    },
}

try:
    context.add_data_docs_site(
        site_name=site_name,
        site_config=site_config,
    )

except Exception as error:
    if "already exists" not in str(error).lower():
        raise


# ==================================================
# 10. CHECKPOINTS
# ==================================================


def get_or_create_checkpoint(checkpoint_name, validation):

    try:
        return context.checkpoints.get(name=checkpoint_name)

    except gx.exceptions.DataContextError:
        checkpoint = gx.Checkpoint(
            name=checkpoint_name,
            validation_definitions=[validation],
        )

        context.checkpoints.add(checkpoint)

        return context.checkpoints.get(name=checkpoint_name)


checkpoint_names = [
    "delivered_orders_checkpoint",
    "fact_orders_checkpoint",
    "fact_orders_business_checkpoint",
    "dim_customers_checkpoint",
    "fact_supplier_shipments_checkpoint",
]

checkpoints = [
    get_or_create_checkpoint(name, validation)
    for name, validation in zip(checkpoint_names, validations)
]


# ==================================================
# 11. RUN VALIDATIONS
# ==================================================

print("\nGREAT EXPECTATIONS DATA QUALITY CHECK")
print("-" * 45)

validation_results = {}

for checkpoint_name, checkpoint in zip(checkpoint_names, checkpoints):

    result = checkpoint.run()

    validation_results[checkpoint_name] = result

    status = "PASSED" if result.success else "FAILED"

    print(f"{checkpoint_name}: {status}")


# ==================================================
# 12. GENERATE HTML REPORT
# ==================================================

context.build_data_docs(site_names=site_name)

report_path = os.path.abspath(
    "./gx_project/uncommitted/data_docs/local_site/index.html"
)

print("\nData Docs report generated.")
print(report_path)


# ==================================================
# 13. PUBLISH RESULTS TO DATAHUB
# ==================================================

publishing_result = publish_gx_results(validation_results)


# ==================================================
# 14. FINAL SUMMARY
# ==================================================

passed = sum(1 for result in validation_results.values() if result.success)

failed = len(validation_results) - passed

print("\nFINAL SUMMARY")
print("-" * 45)
print(f"Checkpoints: {len(validation_results)}")
print(f"Passed: {passed} | Failed: {failed}")
print(f"DataHub assertions published: " f"{publishing_result['published']}")
print(f"Publishing errors: {publishing_result['errors']}")

if failed > 0 or publishing_result["errors"] > 0:
    print("\nCompleted with failures. Check the results above.")
    sys.exit(1)

print("\nAll checks and publishing completed successfully.")
