import os

from dbt_server.lib.set_environment import set_env_vars, set_env_vars_job


def test_set_env_vars():

    os.environ['BUCKET_NAME'] = 'BUCKET'
    os.environ['DOCKER_IMAGE'] = 'IMAGE'
    os.environ['SERVICE_ACCOUNT'] = 'ACCOUNT'
    os.environ['PROJECT_ID'] = 'ID'

    assert set_env_vars() == ('BUCKET', 'IMAGE', 'ACCOUNT', 'ID', 'europe-west9')

    os.environ['LOCATION'] = 'LOCATION'

    assert set_env_vars() == ('BUCKET', 'IMAGE', 'ACCOUNT', 'ID', 'LOCATION')


def test_set_env_vars_job(MockLogging, MockCloudStorage, MockState):
    mock_gcs_client, _, _, _ = MockCloudStorage
    mock_dbt_collection, _ = MockState
    uuid = "UUID"
    mock_logging_client = MockLogging

    os.environ['BUCKET_NAME'] = 'BUCKET'
    os.environ['DBT_COMMAND'] = 'COMMAND'
    os.environ['UUID'] = uuid

    BUCKET_NAME, DBT_COMMAND, UUID, DBT_LOGGER, STATE = set_env_vars_job(mock_gcs_client, mock_dbt_collection,
                                                                         mock_logging_client)
    assert (BUCKET_NAME, DBT_COMMAND, UUID) == ('BUCKET', 'COMMAND', 'UUID')
    assert DBT_LOGGER.uuid == uuid
    assert STATE.uuid == uuid