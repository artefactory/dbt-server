import os
import sys
import msgpack
import json
from typing import TypedDict
import threading
import time

from click.parser import split_arg_string
from dbt.cli.main import dbtRunner, dbtRunnerResult, cli
from dbt.events.base_types import EventMsg
from dbt.events.functions import msg_to_json
from dbt.contracts.graph.manifest import Manifest
from elementary.monitor.cli import report
from fastapi import HTTPException

sys.path.insert(1, './lib')

from state import State
from logger import DbtLogger
from cloud_storage import write_to_bucket


BUCKET_NAME = os.getenv('BUCKET_NAME')
DBT_COMMAND = os.environ.get("DBT_COMMAND")
UUID = os.environ.get("UUID")
ELEMENTARY = os.environ.get("ELEMENTARY")
DBT_LOGGER = DbtLogger(local=False, server=False)
DBT_LOGGER.uuid = UUID


def prepare_and_execute_job(state: State) -> ():
    state.get_context_to_local()

    manifest = get_manifest()
    install_dependencies(state, manifest)

    run_dbt_command(state, manifest, DBT_COMMAND)

    if ELEMENTARY == 'True':
        generate_elementary_report(state)
        upload_elementary_report(state)

    log = "END JOB"
    DBT_LOGGER.log("INFO", log)


def install_dependencies(state: State, manifest: Manifest) -> ():
    packages_path = './packages.yml'
    check_file = os.path.isfile(packages_path)
    if check_file:
        with open('packages.yml', 'r') as f:
            packages_str = f.read()
        if packages_str != '':
            run_dbt_command(state, manifest, 'deps')


def run_dbt_command(state: State, manifest: Manifest, dbt_command: str) -> ():

    state.run_status = "running"

    manifest.build_flat_graph()
    dbt = dbtRunner(manifest=manifest, callbacks=[logger_callback])

    args_list = dbt_command.split(' ')
    res_dbt: dbtRunnerResult = dbt.invoke(args_list)

    if res_dbt.success:
        state.run_status = "success"
    else:
        state.run_status = "failed"
        handle_exception(res_dbt.exception)


def generate_elementary_report(state: State) -> ():
    log = "Generating elementary report..."
    DBT_LOGGER.log("INFO", log)

    report_thread = threading.Thread(target=report, name="Report generator")
    report_thread.start()
    i, timeout = 0, 120
    while report_thread.is_alive() and i < timeout:
        time.sleep(1)
        i += 1

    log = "Report generated!"
    DBT_LOGGER.log("INFO", log)


def upload_elementary_report(state: State) -> ():
    log = "Uploading report..."
    DBT_LOGGER.log("INFO", log)

    cloud_storage_folder = state.storage_folder

    with open('edr_target/elementary_report.html', 'r') as f:
        elementary_report = f.read()
    write_to_bucket(BUCKET_NAME, cloud_storage_folder+"/elementary_report.html", elementary_report)


def logger_callback(event: EventMsg):
    state = State(UUID)
    log_configuration = get_user_request_log_configuration(state.user_command)

    user_log_format = log_configuration['log_format']
    if user_log_format == "json":
        msg = msg_to_json(event)
    else:
        msg = event.info.msg.replace('\n', '  ')

    user_log_level = log_configuration['log_level']
    match event.info.level:
        case "debug":
            if user_log_level == "debug":
                DBT_LOGGER.log(event.info.level.upper(), msg)
            else:
                DBT_LOGGER.logger.debug(msg)

        case "info":
            if user_log_level in ["debug", "info"]:
                DBT_LOGGER.log(event.info.level.upper(), msg)
            else:
                DBT_LOGGER.logger.info(msg)

        case "warn":
            if user_log_level in ["debug", "info", "warn"]:
                DBT_LOGGER.log(event.info.level.upper(), msg)
            else:
                DBT_LOGGER.logger.warn(msg)

        case "error":
            DBT_LOGGER.log(event.info.level.upper(), msg)


LogConfiguration = TypedDict('LogConfiguration', {'log_format': str, 'log_level': str})


def get_user_request_log_configuration(user_command: str) -> LogConfiguration:
    command_args_list = split_arg_string(user_command)
    command_context = cli.make_context(info_name='', args=command_args_list)
    command_params = command_context.params
    return {"log_format": command_params['log_format'], "log_level": command_params['log_level']}


def handle_exception(dbt_exception: BaseException | None):
    DBT_LOGGER.logger.error({"error": dbt_exception})
    if dbt_exception is not None:
        raise HTTPException(status_code=400, detail=dbt_exception)
    else:
        raise HTTPException(status_code=404, detail="dbt command failed")


def get_manifest() -> Manifest:
    with open('manifest.json', 'r') as f:
        manifest_json = json.loads(f.read())
    partial_parse = msgpack.packb(manifest_json)
    manifest: Manifest = Manifest.from_msgpack(partial_parse)
    return manifest


if __name__ == '__main__':

    DBT_LOGGER.log("INFO", "Job started")
    state = State(UUID)
    prepare_and_execute_job(state)
