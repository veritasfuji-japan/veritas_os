"""Call the VERITAS decision endpoint with a minimal example payload."""

import json
import os

from veritas_client import VeritasClient


def main() -> None:
    """Load local configuration and submit a Decision Candidate."""
    client = VeritasClient(
        base_url=os.environ.get("VERITAS_BASE_URL", "http://localhost:8000"),
        api_key=os.environ["VERITAS_API_KEY"],
    )
    response = client.decide(
        {
            "query": "Which maintenance window should an operator review?",
            "options": ["Saturday 02:00 UTC", "Sunday 02:00 UTC"],
        }
    )
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()
