import json
import os
import urllib.error
import urllib.request
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


class DataHubClient:

    def __init__(self):
        self.url = os.getenv("DATAHUB_GMS_URL", "").rstrip("/")
        self.timeout = int(os.getenv("DATAHUB_GRAPHQL_TIMEOUT", "30"))

        if not self.url:
            raise RuntimeError("DATAHUB_GMS_URL is missing from environment variables.")

    def execute(self, query, variables=None):

        payload = json.dumps({"query": query, "variables": variables or {}}).encode(
            "utf-8"
        )

        request = urllib.request.Request(
            f"{self.url}/api/graphql",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:

                result = json.loads(response.read().decode("utf-8"))

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DataHub HTTP error {exc.code}: {detail}") from exc

        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot connect to DataHub: {exc}") from exc

        if result.get("errors"):
            messages = "; ".join(
                error.get("message", str(error)) for error in result["errors"]
            )
            raise RuntimeError(f"DataHub GraphQL error: {messages}")

        return result.get("data", {})
