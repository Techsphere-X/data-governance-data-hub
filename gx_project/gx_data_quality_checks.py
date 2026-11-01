import os
import sys
import great_expectations as gx

# ==================================================
# 1. LOAD GX PROJECT AND CONNECTION
# ==================================================

context = gx.get_context(
    mode="file",
    project_root_dir="./gx_project",
)

connection_string = os.environ.get("POSTGRES_CONNECTION_STRING")

if not connection_string:
    raise EnvironmentError(
        "POSTGRES_CONNECTION_STRING is not set. " "Export it in your terminal first."
    )


# ==================================================
# 2. POSTGRESQL DATA SOURCE
# ==================================================

datasource_name = "olist_postgres"

try:
    data_source = context.data_sources.get(datasource_name)
    print("Reusing existing PostgreSQL data source.")

except LookupError:
    data_source = context.data_sources.add_postgres(
        name=datasource_name,
        connection_string=connection_string,
    )
    print("Created PostgreSQL data source.")


# ==================================================
# 3. HELPER: GET OR CREATE ASSET AND BATCH
# ==================================================


def get_or_create_asset_and_batch(asset_name, query, batch_name):

    try:
        asset = data_source.get_asset(asset_name)
        print(f"Reusing existing asset: {asset_name}")

    except LookupError:
        asset = data_source.add_query_asset(
            name=asset_name,
            query=query,
        )
        print(f"Created asset: {asset_name}")

    try:
        batch_definition = asset.get_batch_definition(batch_name)
        print(f"Reusing existing batch: {batch_name}")

    except LookupError:
        batch_definition = asset.add_batch_definition_whole_table(
            name=batch_name,
        )
        print(f"Created batch: {batch_name}")

    return batch_definition


# ==================================================
# 4. DEFINE QUERIES AND BATCHES
# ==================================================

# A. Delivered orders: missing delivery timestamps

delivered_batch = get_or_create_asset_and_batch(
    asset_name="delivered_orders",
    query="""
        SELECT
            order_id,
            order_delivered_customer_at
        FROM analytics.fact_orders
        WHERE order_status = 'delivered'
    """,
    batch_name="all_delivered_orders",
)


# B. Fact orders: basic quality checks

fact_orders_batch = get_or_create_asset_and_batch(
    asset_name="fact_orders_all",
    query="""
        SELECT
            order_id,
            total_order_value
        FROM analytics.fact_orders
    """,
    batch_name="all_fact_orders",
)


# C. Fact orders: business-rule checks

fact_orders_business_batch = get_or_create_asset_and_batch(
    asset_name="fact_orders_business_rules",
    query="""
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
    batch_name="all_fact_orders_business_rules",
)


# D. Dim customers: customer ID completeness

customers_batch = get_or_create_asset_and_batch(
    asset_name="dim_customers_quality",
    query="""
        SELECT
            customer_id
        FROM analytics.dim_customers
    """,
    batch_name="all_dim_customers",
)


# E. Fact supplier shipments: delivered shipment completeness

shipments_batch = get_or_create_asset_and_batch(
    asset_name="supplier_shipments_quality",
    query="""
        SELECT
            shipment_id,
            shipment_status,
            actual_delivery_date
        FROM analytics.fact_supplier_shipments
        WHERE shipment_status = 'Delivered'
    """,
    batch_name="all_delivered_shipments",
)


# ==================================================
# 5. HELPER: CREATE OR UPDATE EXPECTATION SUITES
# ==================================================


def get_or_create_suite(suite_name, expectations):

    try:
        suite = context.suites.get(name=suite_name)
        print(f"Reusing expectation suite: {suite_name}")

    except gx.exceptions.DataContextError:
        suite = gx.ExpectationSuite(name=suite_name)
        print(f"Created expectation suite: {suite_name}")

    added_count = 0

    for expectation in expectations:

        # Avoid adding the same expectation again on every run.
        if expectation not in suite.expectations:
            suite.add_expectation(expectation)
            added_count += 1

    if added_count > 0:
        context.suites.add_or_update(suite)
        print(f"Added {added_count} expectation(s) to {suite_name}.")

    else:
        print(f"All expectations already exist in {suite_name}.")

    return suite


# ==================================================
# 6. EXPECTATION SUITE 1: DELIVERED ORDERS
# ==================================================

delivered_suite = get_or_create_suite(
    "delivered_orders_quality",
    [
        # Delivered orders must have an actual delivery timestamp.
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="order_delivered_customer_at"
        ),
    ],
)


# ==================================================
# 7. EXPECTATION SUITE 2: FACT ORDERS
# ==================================================

fact_suite = get_or_create_suite(
    "fact_orders_quality",
    [
        # Order ID must not be NULL.
        gx.expectations.ExpectColumnValuesToNotBeNull(column="order_id"),
        # Order ID must be unique.
        gx.expectations.ExpectColumnValuesToBeUnique(column="order_id"),
        # Total order value must not be negative.
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="total_order_value",
            min_value=0,
        ),
    ],
)


# ==================================================
# 8. EXPECTATION SUITE 3: FACT ORDERS BUSINESS RULES
# ==================================================

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
        # Actual delivery date must not be before purchase date.
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="delivery_date_valid",
            value_set=[True],
        ),
        # Order status must belong to the approved list.
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="order_status",
            value_set=approved_order_statuses,
        ),
    ],
)


# ==================================================
# 9. EXPECTATION SUITE 4: DIM CUSTOMERS
# ==================================================

customers_suite = get_or_create_suite(
    "dim_customers_quality",
    [
        # Customer ID must not be NULL.
        gx.expectations.ExpectColumnValuesToNotBeNull(column="customer_id"),
    ],
)


# ==================================================
# 10. EXPECTATION SUITE 5: SUPPLIER SHIPMENTS
# ==================================================

shipments_suite = get_or_create_suite(
    "fact_supplier_shipments_quality",
    [
        # Delivered shipments must have an actual delivery date.
        gx.expectations.ExpectColumnValuesToNotBeNull(column="actual_delivery_date"),
    ],
)


# ==================================================
# 11. VALIDATION DEFINITIONS
# ==================================================


def get_or_create_validation(validation_name, batch_definition, suite):

    try:
        validation = context.validation_definitions.get(name=validation_name)
        print(f"Reusing validation: {validation_name}")

    except gx.exceptions.DataContextError:
        validation = gx.ValidationDefinition(
            name=validation_name,
            data=batch_definition,
            suite=suite,
        )

        context.validation_definitions.add(validation)
        print(f"Created validation: {validation_name}")

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
# 12. DATA DOCS HTML REPORT SITE
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
    print("Created Data Docs site.")

except Exception as error:
    if "already exists" in str(error).lower():
        print("Reusing existing Data Docs site.")
    else:
        raise


# ==================================================
# 13. CHECKPOINTS
# ==================================================


def get_or_create_checkpoint(checkpoint_name, validation):

    try:
        checkpoint = context.checkpoints.get(name=checkpoint_name)
        print(f"Reusing checkpoint: {checkpoint_name}")

    except gx.exceptions.DataContextError:
        checkpoint = gx.Checkpoint(
            name=checkpoint_name,
            validation_definitions=[validation],
        )

        context.checkpoints.add(checkpoint)
        print(f"Created checkpoint: {checkpoint_name}")

    return checkpoint


checkpoint_names = [
    "delivered_orders_checkpoint",
    "fact_orders_checkpoint",
    "fact_orders_business_checkpoint",
    "dim_customers_checkpoint",
    "fact_supplier_shipments_checkpoint",
]

checkpoints = []

for checkpoint_name, validation in zip(checkpoint_names, validations):
    checkpoints.append(get_or_create_checkpoint(checkpoint_name, validation))


# ==================================================
# 14. RUN ALL VALIDATIONS
# ==================================================

validation_results = {}

for checkpoint_name, checkpoint in zip(checkpoint_names, checkpoints):

    print("\n" + "=" * 55)
    print(f"RUNNING: {checkpoint_name.upper()}")
    print("=" * 55)

    result = checkpoint.run()

    validation_results[checkpoint_name] = result

    print("\nVALIDATION RESULT:")
    print(result.describe())


# ==================================================
# 15. GENERATE HTML REPORT
# ==================================================

context.build_data_docs(site_names=site_name)

report_path = os.path.abspath(
    "./gx_project/uncommitted/data_docs/local_site/index.html"
)

print("\n" + "=" * 55)
print("DATA DOCS REPORT")
print("=" * 55)

print("HTML report:", report_path)


# ==================================================
# 16. FINAL VALIDATION SUMMARY
# ==================================================

print("\n" + "=" * 55)
print("FINAL VALIDATION SUMMARY")
print("=" * 55)

all_passed = True

for checkpoint_name, result in validation_results.items():

    status = "PASSED" if result.success else "FAILED"

    print(f"{checkpoint_name}: {status}")

    if not result.success:
        all_passed = False


if all_passed:
    print("\nALL VALIDATIONS PASSED.")

else:
    print("\nSOME VALIDATIONS FAILED.")
    print("Review the individual expectation results and HTML report.")
    sys.exit(1)


print("\nValidation and report generation completed.")
