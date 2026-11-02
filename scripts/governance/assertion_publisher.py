import os
import re
import time

from scripts.governance.datahub_client import DataHubClient

UPSERT_MUTATION = """
mutation UpsertGovernanceAssertion(
    $urn: String!
    $input: UpsertCustomAssertionInput!
) {
    upsertCustomAssertion(
        urn: $urn
        input: $input
    ) {
        urn
    }
}
"""


REPORT_MUTATION = """
mutation ReportGovernanceAssertionResult(
    $urn: String!
    $result: AssertionResultInput!
) {
    reportAssertionResult(
        urn: $urn
        result: $result
    )
}
"""


DELETE_MUTATION = """
mutation DeleteGovernanceAssertion($urn: String!) {
    deleteAssertion(urn: $urn)
}
"""


class AssertionPublisher:

    def __init__(self, client=None):
        self.client = client or DataHubClient()

        self.platform_name = os.getenv(
            "GOVERNANCE_AUDIT_PLATFORM_NAME", "DataHub Governance Audit"
        )

    @staticmethod
    def make_assertion_urn(model_name, rule_key):
        safe_name = (
            re.sub(r"[^a-zA-Z0-9_]+", "_", f"governance_{model_name}_{rule_key}")
            .strip("_")
            .lower()
        )

        return f"urn:li:assertion:{safe_name}"

    def publish(self, entity_urn, model_name, rule_key, description, passed):
        assertion_urn = self.make_assertion_urn(model_name, rule_key)

        assertion_input = {
            "entityUrn": entity_urn,
            "type": "CUSTOM",
            "description": description,
            "platform": {"name": self.platform_name},
        }

        # Create or update the assertion
        self.client.execute(
            UPSERT_MUTATION, {"urn": assertion_urn, "input": assertion_input}
        )

        # Publish the audit result
        result_input = {
            "timestampMillis": int(time.time() * 1000),
            "type": "SUCCESS" if passed else "FAILURE",
        }

        self.client.execute(
            REPORT_MUTATION, {"urn": assertion_urn, "result": result_input}
        )

        return assertion_urn

    def delete(self, model_name, rule_key):
        """Delete a specific governance assertion."""
        assertion_urn = self.make_assertion_urn(model_name, rule_key)

        result = self.client.execute(DELETE_MUTATION, {"urn": assertion_urn})

        print(f"Deleted assertion: {assertion_urn}")

        return result
