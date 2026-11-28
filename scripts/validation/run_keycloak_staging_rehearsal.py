"""Run one isolated Keycloak staging attempt with an operator-controlled resume."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import logging

from veritas_os.api.keycloak_staging_rehearsal import (
    KeycloakStagingRehearsalBlocked,
    keycloak_staging_rehearsal_worker,
    require_staging_rehearsal_environment,
)
from veritas_os.core import shared_halt
from veritas_os.policy.keycloak_lab_executor import KeycloakLabExecutionError

logger = logging.getLogger(__name__)


async def run(factory_ref: str) -> int:
    """Load trusted synthetic inputs and dispatch once after an operator resume."""
    require_staging_rehearsal_environment()
    module_name, separator, factory_name = factory_ref.partition(":")
    if not separator or not module_name or not factory_name.isidentifier():
        raise KeycloakStagingRehearsalBlocked("KEYCLOAK_STAGING_FACTORY_INVALID")
    try:
        factory = getattr(importlib.import_module(module_name), factory_name)
        worker = keycloak_staging_rehearsal_worker(**factory())
    except (ImportError, AttributeError, TypeError) as exc:
        raise KeycloakStagingRehearsalBlocked(
            "KEYCLOAK_STAGING_FACTORY_INVALID"
        ) from exc

    async with worker as dispatch:
        logger.info("Rehearsal worker started. Waiting for an authenticated operator resume.")
        try:
            async with asyncio.timeout(300):
                while (await asyncio.to_thread(shared_halt.status)).get("halted") is not False:
                    await asyncio.sleep(1)
        except (shared_halt.HaltStoreUnavailable, TimeoutError) as exc:
            raise KeycloakStagingRehearsalBlocked(
                "KEYCLOAK_STAGING_OPERATOR_RESUME_UNAVAILABLE"
            ) from exc
        result = await dispatch()
        if result is None:
            logger.info("No dispatch commitment was acknowledged.")
            return 2
        logger.info("Dispatch observation: %s. Confirm effects using independent audit evidence.",
                    result.observation)
        return 0 if result.observation == "HTTP_204_UNVERIFIED" else 2


def main() -> int:
    """Command-line entry point for a trusted, locally provisioned fixture factory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("factory", help="trusted Python module:function supplying synthetic inputs")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        return asyncio.run(run(args.factory))
    except (KeycloakStagingRehearsalBlocked, KeycloakLabExecutionError) as exc:
        logger.error("Staging rehearsal stopped: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
