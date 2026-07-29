from pydantic import BaseModel


class DriverSchema(BaseModel):
    name: str
    key: str
