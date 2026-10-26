from fastapi import APIRouter, Depends
from pydantic import BaseModel

from routeforge.api.deps import require_admin
from routeforge.templates import load_templates

router = APIRouter(prefix="/api/templates", tags=["templates"], dependencies=[Depends(require_admin)])


class TemplateOut(BaseModel):
    id: str
    name: str
    description: str


@router.get("")
def list_templates() -> list[TemplateOut]:
    return [TemplateOut(id=t.id, name=t.name, description=t.description) for t in load_templates().values()]
