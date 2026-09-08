import builtins
import collections
import contextlib
import importlib
import operator
import os
import sys

from fastapi import HTTPException


def process_exception():
    try:
        raise
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))


def import_object(colon_separated_string, accept_live_object=False):
    if not isinstance(colon_separated_string, str):
        # We have been handed the live object itself.
        # Nothing to import. Pass it through.
        return colon_separated_string
    MESSAGE = (
        "Expected string formatted like:\n\n"
        "    package_name.module_name:object_name\n\n"
        "Notice *dots* between modules and a "
        f"*colon* before the object name. Received:\n\n{colon_separated_string!r}"
    )
    import_path, _, obj_path = colon_separated_string.partition(":")
    for segment in import_path.split("."):
        if not segment.isidentifier():
            raise ValueError(MESSAGE)
    for attr in obj_path.split("."):
        if not attr.isidentifier():
            raise ValueError(MESSAGE)
    module = importlib.import_module(import_path)
    return operator.attrgetter(obj_path)(module)


def expand_environment_variables(config):
    """Expand environment variables in a nested config dictionary

    VENDORED FROM dask.config.

    This function will recursively search through any nested dictionaries
    and/or lists.

    Parameters
    ----------
    config : dict, iterable, or str
        Input object to search for environment variables

    Returns
    -------
    config : same type as input

    Examples
    --------
    >>> expand_environment_variables({'x': [1, 2, '$USER']})  # doctest: +SKIP
    {'x': [1, 2, 'my-username']}
    """
    if isinstance(config, collections.abc.Mapping):
        return {k: expand_environment_variables(v) for k, v in config.items()}
    elif isinstance(config, str):
        return os.path.expandvars(config)
    elif isinstance(config, (list, tuple, builtins.set)):
        return type(config)([expand_environment_variables(v) for v in config])
    else:
        return config


def parse(file):
    """
    Given a config file, parse it.

    This wraps YAML parsing and environment variable expansion.
    """
    import yaml

    content = yaml.safe_load(file.read())
    return expand_environment_variables(content)


@contextlib.contextmanager
def prepend_to_sys_path(*paths):
    "Temporarily prepend items to sys.path."

    for item in reversed(paths):
        # Ensure item is str (not pathlib.Path).
        sys.path.insert(0, str(item))
    try:
        yield
    finally:
        for _ in paths:
            sys.path.pop(0)
