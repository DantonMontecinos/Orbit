"""
HTML view routes — serves the Jinja2 dashboard template.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from app.config import settings

router = APIRouter(tags=["views"])

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_templates_dir)), autoescape=True)


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render the main dashboard page."""
    template = _env.get_template("dashboard.html")
    html = template.render(
        router_name=settings.router_name,
        collect_interval=settings.collect_interval_seconds,
    )
    return HTMLResponse(content=html)


@router.get("/wifi", response_class=HTMLResponse)
async def wifi_view(request: Request):
    """Render the WiFi monitoring page."""
    template = _env.get_template("wifi.html")
    html = template.render(
        collect_interval=settings.collect_interval_seconds,
    )
    return HTMLResponse(content=html)


@router.get("/topology", response_class=HTMLResponse)
async def topology_view(request: Request):
    """Render the topology page."""
    template = _env.get_template("topology.html")
    html = template.render(
        collect_interval=settings.collect_interval_seconds,
    )
    return HTMLResponse(content=html)

