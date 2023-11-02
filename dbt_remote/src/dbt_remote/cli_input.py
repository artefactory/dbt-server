from pathlib import Path
import click
from typing import List, Optional
from dataclasses import dataclass

from click.parser import split_arg_string
from dbt.cli.flags import args_to_context
from dbt.cli.main import dbtRunner, dbtRunnerResult, cli as dbt_cli
from dbt.contracts.graph.manifest import Manifest
from dbt.parser.manifest import write_manifest

from src.dbt_remote.cli_local_config import LocalCliConfig
from src.dbt_remote.dbt_server_detector import detect_dbt_server_uri


@dataclass
class CliInput:
    user_command: Optional[str] = None
    args: Optional[List[str]] = ()
    dbt_native_params_overrides: Optional[dict] = None
    command: Optional[str] = None
    manifest: Optional[str] = None
    project_dir: Optional[str] = None
    profiles_dir: Optional[str] = None
    extra_packages: Optional[str] = None
    seeds_path: Optional[str] = None
    server_url: Optional[str] = None
    location: Optional[str] = None
    artifact_registry: Optional[str] = None

    @classmethod
    def from_click_context(cls, ctx):
        default_params = dbt_cli.make_context(info_name="", args=[ctx.info_name] + list(ctx.params["args"])).params
        dbt_native_params = dict(ctx.parent.params, **ctx.params)
        dbt_native_params_overrides = {k: v for k, v in dbt_native_params.items() if k in default_params and v != default_params[k]}
            
        return cls(
            user_command=ctx.info_name,
            args=ctx.params.get('args'),
            dbt_native_params_overrides=dbt_native_params_overrides,
            manifest=ctx.params.get('manifest'),
            project_dir=ctx.params.get('project_dir'),
            profiles_dir=ctx.params.get('profiles_dir'),
            extra_packages=ctx.params.get('extra_packages'),
            seeds_path=ctx.params.get('seeds_path'),
            server_url=ctx.params.get('server_url'),
            location=ctx.params.get('location'),
            artifact_registry=ctx.params.get('artifact_registry')
        )

    def __post_init__(self):
        self.command = self.build_command()
        if self.command in ["image", "submit", "config"]:
            return
            
        self.load_local_config()
        self.profiles_dir = self.find_profiles_dir()
        self.server_url = self.get_server_url()
        self.manifest = self.resolve_manifest()

    def build_command(self) -> str:
        return " ".join([self.user_command] + list(self.args))
    
    def load_local_config(self) -> None:
        local_cli_config = LocalCliConfig().config

        for key in self.__dict__.keys():
            if getattr(self, key) is None and key in local_cli_config:
                setattr(self, key, local_cli_config[key])

        self.project_dir = self.resolve_project_dir()

        for key in self.__dict__.keys():
            if getattr(self, key) is not None and key in ['manifest', 'extra_packages', 'seeds_path']:
                setattr(self, key, str(Path(self.project_dir) / getattr(self, key)))

    def resolve_project_dir(self) -> str:
        
        project_yaml_path = (Path(self.project_dir) / "dbt_project.yml").absolute()
        if not project_yaml_path.exists():
            raise click.ClickException(f"{click.style('ERROR', fg='red')}\tNo dbt_project.yml found at expected path '{project_yaml_path}'")
        return str(Path(self.project_dir).absolute())

    def find_profiles_dir(self) -> str:
        if "--profiles-dir" in self.command:
            profiles_dir = Path(self.get_profiles_dir_from_command()).absolute()

            if (profiles_dir / "profiles.yml").exists():
                return str(profiles_dir)
            else:
                raise click.ClickException(f"{click.style('ERROR', fg='red')}\tNo profiles.yml file found at '{profiles_dir}'")
        
        if (Path.cwd() / "profiles.yml").exists():
            return str(Path.cwd().absolute())
        elif (Path.home() / ".dbt" / "profiles.yml").exists(): 
            return str(Path.home().absolute() / ".dbt")
        else:
            raise click.ClickException(f"{click.style('ERROR', fg='red')}\tNo profiles.yml file found.")

    def get_server_url(self) -> str:
        if self.server_url is None:
            server_url  = detect_dbt_server_uri(self.location)
            click.echo(f"Detected dbt server at: {click.style(server_url, blink=True, bold=True)}")
            if click.confirm("Do you want to use this server as your default dbt server for this project?", default=True):
                set([f'server_url={server_url}'])
        else:
            server_url = self.server_url
        return server_url
    
    def resolve_manifest(self) -> str:
        if self.manifest is not None:
            return str(Path(self.manifest).absolute())
        
        click.echo("\nGenerating manifest.json")
        target_dir = Path(self.project_dir) / 'target'
        target_dir.mkdir(parents=True, exist_ok=True)

        res: dbtRunnerResult = dbtRunner().invoke(["parse", "--project-dir", self.project_dir, "--profiles-dir", self.profiles_dir])
        manifest: Manifest = res.result
        write_manifest(manifest, str(target_dir))
        return str(target_dir.absolute())
            
    def get_profiles_dir_from_command(self) -> str:
        dbt_command = self.sanitize_command()
        args_list = split_arg_string(dbt_command)
        sub_command_context = args_to_context(args_list)
        sub_command_params_dict = sub_command_context.params
        return sub_command_params_dict["profiles_dir"]
