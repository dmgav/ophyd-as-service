================
ophyd-as-service
================

Prototype for REST API Server for Ophyd devices


Starting the server::

    uvicorn --host localhost --port 60620 ophyd_as_service.server:app


Starting the server with config file::

    OPHYD_AS_SERVICE_SERVER_CONFIG=config.yml uvicorn --host localhost --port 60620 ophyd_as_service.server:app
