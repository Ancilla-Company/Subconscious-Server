import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


_templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=_templates_dir)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
  return templates.TemplateResponse(request, "index.html", {"active_page": "home"})

@router.get("/features", response_class=HTMLResponse)
async def features(request: Request):
  return templates.TemplateResponse(request, "features.html", {"active_page": "features"})

@router.get("/blog", response_class=HTMLResponse)
async def blog(request: Request):
  return templates.TemplateResponse(request, "blog.html", {"active_page": "blog"})

@router.get("/blog/{slug}", response_class=HTMLResponse)
async def blog_post(request: Request, slug: str):
  return templates.TemplateResponse(request, "article.html", {"active_page": "blog"})
