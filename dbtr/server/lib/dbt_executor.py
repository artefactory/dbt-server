import logging
from pathlib import Path
import time
from typing import Any, List

from dbt.cli.main import dbtRunner, dbtRunnerResult
from dbt.contracts.graph.manifest import Manifest
from dbtr.server.config import CONFIG
from dbtr.server.lib.database import Database

from dbtr.server.lib.lock import Lock


class DBTExecutor:
    LOG_CONFIG = {"log_format_file": "json", "log_level": "none", "log_level_file": "debug"}

    def __init__(
            self,
            dbt_runtime_config,
            server_runtime_config,
            artifact_input: Path,
            logger: logging.Logger,
    ):
        self.dbt_runtime_config = dbt_runtime_config
        self.server_runtime_config = server_runtime_config
        self.artifact_input = artifact_input
        self.logger = logger

    def execute_command(self, dbt_command: List[str], lock: Lock = None):
        try:
            with Database(CONFIG.db_connection_string, logger=self.logger) as db:
                db.execute(
                    "INSERT INTO Runs (run_id, start_time, run_status) VALUES (?, ?, ?)",
                    (self.server_runtime_config["run_id"], time.time(), "initializing")
                )
            command_args = self.__prepare_command_args(self.dbt_runtime_config, self.artifact_input)
            self.logger.info("Building manifest")
            manifest = self.__generate_manifest(command_args)
            self.logger.info(f"Executing dbt command {dbt_command} with artifact input {self.artifact_input.as_posix()}")
            with Database(CONFIG.db_connection_string, logger=self.logger) as db:
                db.execute(
                    "UPDATE Runs SET run_status = 'running' WHERE run_id = ?",
                    (self.server_runtime_config["run_id"],)
                )
            dbt_runner = dbtRunner(manifest=manifest)
            result = dbt_runner.invoke(dbt_command, **{**command_args, **self.LOG_CONFIG})
            final_run_status = "success" if result.success else "failed"
            self.logger.info(f"DBT command {dbt_command} completed")
            with Database(CONFIG.db_connection_string, logger=self.logger) as db:
                db.execute(
                    "UPDATE Runs SET end_time = ?, run_status = ? WHERE run_id = ?",
                    (time.time(), final_run_status, self.server_runtime_config["run_id"])
                )
        except Exception as e:
            self.logger.error(f"Failed to execute dbt command {dbt_command}: {e}")
            with Database(CONFIG.db_connection_string, logger=self.logger) as db:
                db.execute(
                    "UPDATE Runs SET end_time = ?, run_status = ? WHERE run_id = ?",
                    (time.time(), "server error", self.server_runtime_config["run_id"])
                )
            raise
        finally:
            if lock:
                lock.release()

    @staticmethod
    def __prepare_command_args(command_args: dict[str, Any], remote_project_dir: Path) -> dict[str, Any]:
        args = {key: val for key, val in command_args.items() if not key.startswith("deprecated")}
        args.pop("warn_error_options", None)  # TODO: define how to handle this
        args.pop("args", None)
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
