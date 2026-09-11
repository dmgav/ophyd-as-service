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

Sample config file::

    worker_configuration:
        startup_dir: .
        existing_plans_and_devices_path: existing_plans_and_devices.yaml
        user_group_permissions_path: user_group_permissions.yaml
        use_ipython_kernel: true
        ipython_kernel_ip: auto
        ipython_matplotlib: Agg
        ipython_connection_file: connection_file.json,
        ipython_connection_dir: /tmp
        ipython_shell_port: 60000
        ipython_iopub_port: 60001
        ipython_stdin_port: 60002
        ipython_hb_port: 60003
        ipython_control_port: 60004
    authentication:
        single_user_api_key: a
