from pydantic import BaseModel


class SharedAccessCreateRequest(BaseModel):
    regenerate: bool = False

