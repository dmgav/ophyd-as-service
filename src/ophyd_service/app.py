import asyncio
import collections
import importlib
import logging
import os
import pprint
import re
import secrets
import urllib.parse
from functools import lru_cache, partial

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from .resources import SERVER_RESOURCES as SR
from .routers import core_api

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

logging.basicConfig(level=logging.WARNING)
logging.getLogger(__name__).setLevel("DEBUG")


def custom_openapi(app):
    """
    The app's openapi method will be monkey-patched with this.

    This is the approach the documentation recommends.

    https://fastapi.tiangolo.com/advanced/extending-openapi/
    """
    from . import __version__

    if app.openapi_schema:
        return app.openapi_schema
    # Customize heading.
    openapi_schema = get_openapi(
        title="Bluesky HTTP Server",
        version=__version__,
        description="Control Experiments using Bluesky Queue Server",
        routes=app.routes,
    )
    # print(f"openapi_schema = {pprint.pformat(openapi_schema['components'])}")  ##
    # Insert refreshUrl.
    if "securitySchemes" in openapi_schema["components"]:  # False when calling /docs
        openapi_schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"]["password"][
            "refreshUrl"
        ] = "token/refresh"
    app.openapi_schema = openapi_schema
    return app.openapi_schema


def add_router(app, *, module_and_router_name):
    """
    Include a router specified by module and router name represented as a string.

    Parameters
    ----------
    app: FastAPI
        Instantiated ``FastAPI`` object.
    module_and_router_name: str
        Name of the module and router object represented as a string, e.g. ``'some.module.router'``,
        where ``some.module`` is the module name and ``router`` is the name of the router object
        in the module.

    Raises
    ------
    ImportError
        Failed to include router, most likely because the module could not be imported or the router
        is not found.
    """
    try:
        components = module_and_router_name.split(".")
        if len(components) < 2:
            raise ValueError(
                f"Module name or router name is not found in {module_and_router_name!r}: "
                "expected format '<module-name>.<router-name>'"
            )
        module_name = ".".join(components[:-1])
        router_name = components[-1]
        mod = importlib.import_module(module_name)
        router = getattr(mod, router_name)
        app.include_router(router)
    except Exception as ex:
        raise ImportError(f"Failed to import router {module_and_router_name!r}: {ex}") from ex


def build_app(server_settings=None):
    """
    Build application

    Parameters
    ----------
    authentication: dict, optional
        Dict of authentication configuration.
    server_settings: dict, optional
        Dict of other server configuration.
    """

    app = FastAPI()

    # Include standard routers
    app.include_router(core_api.router)

    # Include custom routers
    router_names = []
    router_names_str = os.getenv("OPHYD_SERVICE_CUSTOM_ROUTERS", None)
    if "custom_routers" in server_settings["server_configuration"]:
        router_names = server_settings["server_configuration"]["custom_routers"]
        logger.info("Custom routers are specified in the config file: %s", router_names)
    elif router_names_str:
        router_names = re.split(":|,", router_names_str)
        logger.info("Custom routers are specified in the environment variable: %s", router_names)

    if router_names:
        routers_already_included = set()
        for rn in router_names:
            if rn and (rn not in routers_already_included):
                logger.info("Including custom router '%s' ...", rn)
                routers_already_included.add(rn)
                add_router(app, module_and_router_name=rn)
        logger.info("All custom routers are included successfully.")

    @app.on_event("startup")
    async def startup_event():
        # Stash these to cancel this on shutdown.
        app.state.tasks = []

        server_config = (server_settings or {}).get("server_configuration", {}) or {}
        SR.setup_environment_manager(
            worker_config=server_config.get("worker_configuration", {}),
            user_group_permissions_path=server_config.get("user_group_permissions_path"),
        )

        # The following message is used in unit tests to detect when HTTP server is started.
        #   Unit tests need to be modified if this message is modified.
        logger.info("Ophyd-Service server started successfully")

    @app.on_event("shutdown")
    async def shutdown_event():
        """Safely shutdown and perform the cleanup robustly

        This change ensures that the application shuts down and cleans up resources even if there is
        a problem, without silencing the errors.
        """
        # Leaving the worker process running would orphan it.
        if SR.environment_manager.is_running:
            success, msg = await SR.environment_manager.close_environment()
            if not success:
                logger.error("Failed to close the RE Worker environment: %s", msg)

        for task in getattr(app.state, "tasks", []):
            task.cancel()


    return app
