"""
Management of the worker environment (worker process lifecycle).

The server process owns the communication pipe and the worker process. There is no
watchdog process: the worker is started, monitored and stopped directly from the
process that runs the FastAPI server.
"""

import asyncio
import enum
import logging
import multiprocessing
import time as ttime

from bluesky_queueserver.manager.comms import PipeJsonRpcSendAsync
from bluesky_queueserver.manager.profile_ops import load_user_group_permissions

from .worker import RunEngineWorker

logger = logging.getLogger(__name__)

# Maximum time to wait for the worker to exit in an orderly way before it is killed.
DEFAULT_CLOSE_TIMEOUT = 10.0
# Time to let the pipe polling threads exit before the connections are closed.
_COMM_STOP_DELAY = 0.25


class EnvState(enum.Enum):
    CLOSED = "closed"
    OPENING = "opening"
    OPEN = "open"
    CLOSING = "closing"


def default_worker_config():
    """
    Default configuration of the worker process. The worker fails to start unless all
    the keys are present, so the defaults are used for the parameters that are not
    explicitly configured.
    """
    return {
        "use_ipython_kernel": False,
        # Startup code: exactly one of the three sources must be set (Python mode).
        "startup_dir": None,
        "startup_module_name": None,
        "startup_script_path": None,
        "startup_profile": None,
        "ipython_dir": None,
        "ipython_matplotlib": None,
        "user_group_permissions_path": "user_group_permissions.yaml",
        "existing_plans_and_devices_path": None,
        "update_existing_plans_devices": "NEVER",
        "ignore_invalid_plans": False,
        "device_max_depth": 0,
        "ipython_kernel_ip": "localhost",
        "ipython_connection_file": None,
        "ipython_connection_dir": None,
        "ipython_shell_port": None,
        "ipython_iopub_port": None,
        "ipython_stdin_port": None,
        "ipython_hb_port": None,
        "ipython_control_port": None,
    }


class EnvironmentManager:
    """
    Starts, monitors and stops the worker process.

    Parameters
    ----------
    worker_config: dict or None
        Configuration of the worker process. Overrides ``default_worker_config()``.
    close_timeout: float
        Maximum time to wait for the orderly exit before the process is killed.
    log_level: int
        Log level passed to the worker process.
    """

    def __init__(
        self,
        *,
        worker_config=None,
        close_timeout=DEFAULT_CLOSE_TIMEOUT,
        log_level=logging.INFO,
    ):
        self._worker_config = default_worker_config()
        self._worker_config.update(worker_config or {})

        self._close_timeout = close_timeout
        self._log_level = log_level

        self._process = None
        self._conn_server, self._conn_worker = None, None
        self._comm_to_worker = None

        # The queue is owned by the server process and reused by each new worker process.
        self._msg_queue = multiprocessing.Queue()

        self._state = EnvState.CLOSED
        # Serializes the open/close operations, which may be requested concurrently.
        self._lock = asyncio.Lock()

    @property
    def state(self):
        return self._state.value

    @property
    def msg_queue(self):
        return self._msg_queue

    @property
    def is_running(self):
        return (self._process is not None) and self._process.is_alive()

    # ------------------------------------------------------------
    #                        Open environment

    async def open_environment(self):
        """
        Start the worker process and wait until the environment is ready. Returns
        ``(success, err_msg)``.
        """

        def _validate_startup_config():
            """
            In Python mode the startup code is loaded by the worker using
            ``load_worker_startup_code()``, which requires exactly one source to be specified.
            """
            if self._worker_config["use_ipython_kernel"]:
                return

            keys = ("startup_dir", "startup_module_name", "startup_script_path")
            if sum(self._worker_config.get(_) is not None for _ in keys) != 1:
                raise ValueError(
                    "Exactly one source of startup code ('startup_dir', 'startup_module_name' "
                    "or 'startup_script_path') must be configured."
                )

        async def _start_worker(user_group_permissions):
            self._conn_server, self._conn_worker = multiprocessing.Pipe()

            self._process = RunEngineWorker(
                conn=self._conn_worker,
                msg_queue=self._msg_queue,
                name="Worker Process",
                config=self._worker_config,
                log_level=self._log_level,
                user_group_permissions=user_group_permissions,
            )
            await asyncio.to_thread(self._process.start)

            # The object must be created in the running loop.
            self._comm_to_worker = PipeJsonRpcSendAsync(
                conn=self._conn_server,
                use_json=False,
                name="Server-Worker Comm",
            )
            self._comm_to_worker.start()

        async def _wait_until_ready():
            """
            Poll the worker state until the environment is ready. Loading of the startup code
            may take arbitrarily long time, so no timeout is applied. The worker switches to
            the 'closing' state if it fails to load the startup code.
            """
            while True:
                if not self.is_running:
                    return False, "Worker process terminated unexpectedly while opening the environment."

                status = await self._request_worker_state()
                env_state = status.get("environment_state") if status else None

                if env_state == "idle":
                    return True, ""
                if env_state in ("failed", "closing"):
                    return False, "Failed to load the startup code."

                await asyncio.sleep(0.2)


        async with self._lock:
            if (self._state != EnvState.CLOSED) or self.is_running:
                return False, "RE Worker environment already exists."

            try:
                _validate_startup_config()
                # Permissions are loaded from disk before the process is created.
                user_group_permissions_path = self._worker_config.get("user_group_permissions_path")
                user_group_permissions = await asyncio.to_thread(
                    load_user_group_permissions, user_group_permissions_path
                )
            except Exception as ex:
                logger.exception("Failed to open RE Worker environment: %s", ex)
                return False, f"Failed to open RE Worker environment: {ex}"

            self._state = EnvState.OPENING
            logger.info("Opening RE Worker environment ...")

            try:
                await _start_worker(user_group_permissions)
                success, err_msg = await _wait_until_ready()
            except Exception as ex:
                logger.exception("Failed to start RE Worker process: %s", ex)
                success, err_msg = False, f"Failed to start RE Worker process: {ex}"

            if success:
                self._state = EnvState.OPEN
                logger.info("RE Worker environment was opened successfully")
            else:
                logger.error("Failed to open RE Worker environment: %s", err_msg)
                await self._destroy_worker()
                self._state = EnvState.CLOSED

            return success, err_msg


    # ------------------------------------------------------------
    #                       Close environment

    async def close_environment(self):
        """
        Close the environment in an orderly way. The worker process is killed if it fails
        to exit before the timeout expires. Returns ``(success, err_msg)``.
        """

        async def _close_worker(deadline):
            try:
                response = await self._comm_to_worker.send_msg("command_close_env")
            except Exception as ex:
                return False, f"Failed to send the request to close the environment: {ex}"

            if response.get("status") != "accepted":
                return False, response.get("err_msg") or "The request to close the environment was rejected."

            # Wait until the worker is ready to exit and is waiting for the confirmation.
            while ttime.monotonic() < deadline:
                if not self.is_running:
                    return True, ""
                status = await self._request_worker_state()
                if status and status.get("environment_state") == "closing":
                    break
                await asyncio.sleep(0.1)
            else:
                return False, "Timeout while waiting for the worker to prepare to exit."

            try:
                await self._comm_to_worker.send_msg("command_confirm_exit")
            except Exception as ex:
                return False, f"Failed to confirm exit of the worker process: {ex}"

            timeout = max(deadline - ttime.monotonic(), 0)
            await asyncio.to_thread(self._process.join, timeout)

            if self.is_running:
                return False, "Timeout while waiting for the worker process to exit."

            return True, ""

        async def _cleanup():
            if self._comm_to_worker is not None:
                self._comm_to_worker.stop()
                self._comm_to_worker = None
                # The polling threads raise an error if the connection is closed while in use.
                await asyncio.sleep(_COMM_STOP_DELAY)

            for conn in (self._conn_server, self._conn_worker):
                try:
                    if conn is not None:
                        conn.close()
                except Exception as ex:
                    logger.debug("Failed to close the communication pipe: %s", ex)

            self._conn_server, self._conn_worker = None, None
            self._process = None

        async def _destroy_worker():
            """
            Kill the worker process and release the resources.
            """
            if self.is_running:
                logger.warning("Killing the worker process ...")
                try:
                    self._process.kill()
                    await asyncio.to_thread(self._process.join)
                except Exception as ex:
                    logger.exception("Failed to kill the worker process: %s", ex)

            await _cleanup()

        async with self._lock:
            if (self._state != EnvState.OPEN) or not self.is_running:
                return False, "RE Worker environment does not exist."

            self._state = EnvState.CLOSING
            logger.info("Closing RE Worker environment ...")

            deadline = ttime.monotonic() + self._close_timeout
            success, err_msg = await _close_worker(deadline)

            if not success or self.is_running:
                logger.error("Failed to close RE Worker environment in an orderly way: %s", err_msg)
                await _destroy_worker()
                success, err_msg = True, f"The worker process was killed: {err_msg}"
            else:
                await _cleanup()
                logger.info("RE Worker environment was closed successfully")

            self._state = EnvState.CLOSED
            return success, err_msg


    # ------------------------------------------------------------

    async def _request_worker_state(self):
        try:
            return await self._comm_to_worker.send_msg("request_state")
        except Exception as ex:
            logger.debug("Failed to load the worker state: %s", ex)
            return None


