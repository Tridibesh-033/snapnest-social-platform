from typing import Optional
from pydantic import BaseModel
from fastapi_users import schemas
import uuid


class PostCreate(BaseModel):
    title: str
    content: str

class UserRead(schemas.BaseUser[uuid.UUID]):
    email: str
    username:str

class UserCreate(schemas.BaseUserCreate):
    email: str
    password: str
    username: str
    
class UserUpdate(schemas.BaseUserUpdate):
    username: Optional[str]=None
