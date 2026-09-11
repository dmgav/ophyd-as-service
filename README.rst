=============
ophyd-service
=============

Prototype for REST API Server for Ophyd devices


Starting the server::

    uvicorn --host localhost --port 60620 ophyd_service.server:app


Starting the server with config file::

    OPHYD_SERVICE_CONFIG=config.yml uvicorn --host localhost --port 60620 ophyd_service.server:app

Starting with single user API key::

    OPHYD_SERVICE_SINGLE_USER_API_KEY=a uvicorn --host localhost --port 60620 ophyd_service.server:app

The API can be accessed as following:: 

    http GET http://localhost:60620/api/ping 'Authorization: ApiKey a'