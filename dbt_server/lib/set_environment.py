import os
from typing import List
from google.cloud.logging import Client
from google.cloud import firestore
import yaml

from lib.state import State
from lib.logger import DbtLogger
from lib.cloud_storage import CloudStorage

with open("lib/server_default_config.yml", 'r') as f:
    SERVER_DEFAULT_CONFIG = yaml.safe_load(f)


def set_env_vars() -> tuple[str | None, str | None, str | None, str | None, str | None]:
    BUCKET_NAME = os.getenv('BUCKET_NAME', default=SERVER_DEFAULT_CONFIG["bucket_name"])
    DOCKER_IMAGE = os.getenv('DOCKER_IMAGE', default=SERVER_DEFAULT_CONFIG["docker_image"])
    SERVICE_ACCOUNT = os.getenv('SERVICE_ACCOUNT', default=SERVER_DEFAULT_CONFIG["service_account"])
    PROJECT_ID = os.getenv('PROJECT_ID', default=SERVER_DEFAULT_CONFIG["project_id"])
    LOCATION = os.getenv('LOCATION', default=SERVER_DEFAULT_CONFIG["location"])
    return BUCKET_NAME, DOCKER_IMAGE, SERVICE_ACCOUNT, PROJECT_ID, LOCATION


def set_env_vars_job(cloud_storage_instance: CloudStorage,
                     dbt_collection: firestore.CollectionReference,
                     logging_client: Client) -> tuple[str | None, str | None, str | None,
                                                      DbtLogger, State]:
    BUCKET_NAME = os.getenv('BUCKET_NAME', default=SERVER_DEFAULT_CONFIG["bucket_name"])
    DBT_COMMAND = os.environ.get("DBT_COMMAND", default='')
    UUID = os.environ.get("UUID", default='0000')
    DBT_LOGGER = DbtLogger(cloud_storage_instance=cloud_storage_instance, dbt_collection=dbt_collection,
                           logging_client=logging_client, local=False, server=False)
    DBT_LOGGER.uuid = UUID
    STATE = State(UUID, cloud_storage_instance, dbt_collection)
    return BUCKET_NAME, DBT_COMMAND, UUID, DBT_LOGGER, STATE


def get_server_dbt_logger(client_storage_instance: CloudStorage, dbt_collection: firestore.CollectionReference,
                          logging_client: Client, argv: List[str]) -> DbtLogger:
    local = False
    if len(argv) == 2 and argv[1] == "--local":  # run locally:
        local = True
    DBT_LOGGER = DbtLogger(cloud_storage_instance=client_storage_instance, dbt_collection=dbt_collection,
                           logging_client=logging_client, local=local, server=True)
    return DBT_LOGGER