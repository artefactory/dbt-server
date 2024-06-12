import logging
import threading
from pathlib import Path
from typing import Any

from dbt.cli.main import dbtRunner, dbtRunnerResult
from dbt.contracts.graph.manifest import Manifest

manifest_lock = threading.Lock()


class DBTExecutor:
    LOG_CONFIG = {"log_format_file": "json", "log_level": "none", "log_level_file": "debug"}

    def __init__(
            self,
            dbt_runtime_config,
            artifact_input: Path,
            logger: logging.Logger,
    ):
        self.dbt_runtime_config = dbt_runtime_config
        self.artifact_input = artifact_input
        self.logger = logger

    def execute_command(self, dbt_command: str):
        command_args = self.__prepare_command_args(self.dbt_runtime_config, self.artifact_input)
        with manifest_lock:
            self.logger.info("Building manifest")
            manifest = self.__generate_manifest(command_args)
        dbt_runner = dbtRunner(manifest=manifest)
        dbt_runner.invoke([dbt_command], **{**command_args, **self.LOG_CONFIG})

    @staticmethod
    def __prepare_command_args(command_args: dict[str, Any], remote_project_dir: Path) -> dict[str, Any]:
        args = {key: val for key, val in command_args.items() if not key.startswith("deprecated")}
        args.pop("warn_error_options", None)  # TODO: define how to handle this
        if "project_dir" in command_args:
            args["project_dir"] = remote_project_dir.as_posix()
        if "profiles_dir" in command_args:
            args["profiles_dir"] = remote_project_dir.as_posix()
        if not command_args.get("select", None):
            args["select"] = ()
        if not command_args.get("exclude", None):
            args["exclude"] = ()
        return args

    def __generate_manifest(self, command_args: dict) -> Manifest:
        res: dbtRunnerResult = dbtRunner().invoke(
            ["parse"],
            **{**command_args, **self.LOG_CONFIG, "log_level_file": "none"}  # log ignored here to
        )
        if not res.success:
            raise res.exception
        manifest: Manifest = res.result
        manifest.build_flat_graph()
        return manifest
