import requests
from typing import Dict, List
import json
import yaml

import click
from click.parser import split_arg_string
from dbt.cli.flags import args_to_context
from google.cloud import run_v2


def detect_dbt_server_uri(project_dir: str, dbt_project: str, command: str, location: str | None) -> str:

    project_id, location = identify_project_id_and_location(project_dir, dbt_project, command, location)

    cloud_run_services = get_cloud_run_service_list(project_id, location)
    for service in cloud_run_services:
        if check_if_server_is_dbt_server(service):
            click.echo('Using Cloud Run `' + service.name + '` as dbt server')
            click.echo('uri: ' + service.uri)
            return service.uri

    click.echo(click.style("ERROR", fg="red"))
    raise click.ClickException('No dbt server found in Cloud Run')


def identify_project_id_and_location(project_dir: str, dbt_project: str, command: str,
                                     location: str | None) -> (str, str):

    profiles_dict = read_yml_file(project_dir + '/profiles.yml')
    selected_profile = get_selected_sub_command_conf_from_user_command(command, 'profile')
    selected_target = get_selected_sub_command_conf_from_user_command(command, 'target')

    if selected_profile is None:
        selected_profile = read_yml_file(project_dir + '/' + dbt_project)['profile']
    if selected_profile not in profiles_dict.keys():
        click.echo(click.style("ERROR", fg="red"))
        raise click.ClickException('Profile: ' + selected_profile + ' not found in profiles.yml')

    if selected_target is None:
        selected_target = deduce_target_from_profiles(profiles_dict[selected_profile])
    if selected_target not in profiles_dict[selected_profile]['outputs'].keys():
        click.echo(click.style("ERROR", fg="red"))
        raise click.ClickException('Target: "'+selected_target+'" not found for profile '+selected_profile)

    project_id = get_metadata_from_profiles_dict(profiles_dict, selected_profile, selected_target, 'project')
    if location is None:
        location = get_metadata_from_profiles_dict(profiles_dict, selected_profile, selected_target, 'location')

    return project_id, location


def get_selected_sub_command_conf_from_user_command(command: str, config_field_name: str) -> str | None:
    """
        config_field_name should be keys from sub_command context
        ex: target, profile
    """
    try:
        args_list = split_arg_string(command)
        sub_command_click_context = args_to_context(args_list)
        if config_field_name not in sub_command_click_context.params.keys():
            click.echo(click.style("ERROR", fg="red"))
            raise click.ClickException(config_field_name + " not in context.params")
        else:
            return sub_command_click_context.params[config_field_name]
    except Exception:
        click.echo(click.style("ERROR", fg="red"))
        raise click.ClickException("dbt command failed: " + command)


def deduce_target_from_profiles(selected_profile_dict: Dict[str, str]) -> str:
    if 'target' in selected_profile_dict.keys():
        return selected_profile_dict['target']
    elif 'outputs' in selected_profile_dict.keys():
        if 'default' in selected_profile_dict['outputs'].keys():
            return 'default'
        else:
            return list(selected_profile_dict['outputs'].keys())[0]
    else:
        click.echo(click.style("ERROR", fg="red"))
        raise click.ClickException('Coulnd\'t find any target in for given profile')


def get_metadata_from_profiles_dict(profiles_dict: Dict[str, str], selected_profile: str, selected_target: str,
                                    metadata_name: str) -> str:
    """
        metadata_name corresponds to project/data information for a given profile and target
        ex: location, project_id, dataset, type, etc.
    """

    profile_config = profiles_dict[selected_profile]['outputs'][selected_target]
    if metadata_name not in profile_config.keys():
        click.echo(click.style("ERROR", fg="red"))
        raise click.ClickException(metadata_name + ' not found for profile '+selected_profile+' and \
                                    target '+selected_target)
    metadata = profile_config[metadata_name]
    return metadata


def get_cloud_run_service_list(project_id: str, location: str) -> List[run_v2.types.service.Service]:
    click.echo(f"Cloud Run location: {location}")

    client = run_v2.ServicesClient()

    parent_value = f"projects/{project_id}/locations/{location}"
    request = run_v2.ListServicesRequest(
        parent=parent_value,
    )

    service_list = client.list_services(request=request)
    return service_list


def check_if_server_is_dbt_server(service: run_v2.types.service.Service) -> bool:
    url = service.uri + '/check'
    try:
        res = requests.get(url)
    except Exception:  # request timeout or max retries
        return False
    if res.status_code == 200:
        try:
            check = json.loads(res.text)['response']
            if 'Running dbt-server on port' in check:
                return True
            else:
                return False
        except Exception:
            return False
    else:
        return False


def read_yml_file(filename: str) -> Dict[str, str]:
    with open(filename, 'r') as stream:
        try:
            d = yaml.safe_load(stream)
            return d
        except yaml.YAMLError as e:
            click.echo(click.style("ERROR", fg="red") + '\t' + filename + " is not a correct YAML file")
            raise click.ClickException(e)
