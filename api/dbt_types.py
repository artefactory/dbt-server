from pydantic import BaseModel


class dbt_command(BaseModel):
    command: str
    manifest: str
    dbt_project: str