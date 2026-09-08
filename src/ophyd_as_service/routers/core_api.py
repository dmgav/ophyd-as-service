import asyncio
import io
import logging
import pprint

import pydantic
from fastapi import APIRouter, Depends, File, Form, Request, Security, UploadFile, WebSocket, WebSocketDisconnect
from packaging import version

from ophyd_as_service import __version__

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
async def ping_handler(payload: dict = {}):
    """
    May be called to get some response from the server. Currently returns status of RE Manager.
    """
    msg = {"success": True, "msg": f"Ophyd-As-Service: v.{__version__}"}
    return msg
