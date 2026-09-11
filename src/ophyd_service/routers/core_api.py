import logging

from fastapi import APIRouter, Security

from ophyd_service import __version__

from ..authentication import get_current_principal
from ..resources import SERVER_RESOURCES as SR

# if version.parse(pydantic.__version__) < version.parse("2.0.0"):
#     from pydantic import BaseSettings
# else:
#     from pydantic_settings import BaseSettings

# from ..resources import SERVER_RESOURCES as SR
# from ..utils import process_exception

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.get("/")
@router.get("/ping")
async def ping_handler(payload: dict = {}, principal=Security(get_current_principal, scopes=["read:status"])):
    """
    May be called to get some response from the server. Currently returns status of RE Manager.
    """
    msg = {"success": True, "msg": f"Ophyd-Service: v.{__version__}"}
    return msg


@router.get("/device/{device_name:path}")
async def device_name_handler(device_name: str, principal=Security(get_current_principal, scopes=["read:status"])):
    """
    Return the name of the device. The name may contain slashes.
    """
    logger.info("Device name: %s", device_name)
    return {"success": True, "msg": "", "device_name": device_name}


@router.post("/environment/open")
async def environment_open_handler(principal=Security(get_current_principal, scopes=["write:manager:control"])):
    """
    Open the RE Worker environment: start the worker process and load the startup code.
    """
    success, msg = await SR.environment_manager.open_environment()
    return {"success": success, "msg": msg}


@router.post("/environment/close")
async def environment_close_handler(principal=Security(get_current_principal, scopes=["write:manager:control"])):
    """
    Close the RE Worker environment. The worker process is killed if it fails to exit
    in an orderly way before the timeout expires.
    """
    success, msg = await SR.environment_manager.close_environment()
    return {"success": success, "msg": msg}
