=============
ophyd-service
=============

Prototype for REST API Server for Ophyd devices


Starting the server::

    uvicorn --host localhost --port 60620 ophyd_service.server:app


Starting the server with config file::

    OPHYD_SERVICE_CONFIG=config.yml uvicorn --host localhost --port 60620 ophyd_service.server:app
