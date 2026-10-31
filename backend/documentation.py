"""Read-only, server-rendered project documentation from the tracked Markdown files."""
from html import escape
from pathlib import Path
import re
from urllib.parse import quote, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'docs'
PAGES = (
    ('index', 'README.md', '문서 안내'),
    ('project-guide', 'project-guide.md', '프로젝트 안내'),
    ('analysis-and-upstream', 'analysis-and-upstream.md', '분석 방법 · 원본 저장소'),
    ('current-baselines', 'current-baselines.md', '현재 기준선'),
    ('baseline-update', 'baseline-update.md', '기준선 업데이트'),
    ('architecture-and-api', 'architecture-and-api.md', '구조 · 데이터 · API'),
    ('render-deployment', 'render-deployment.md', '배포 · 데이터 보관'),
    ('developer-proposals', 'developer-proposals.md', '개발자 제안'),
)
router = APIRouter(prefix='/guide', include_in_schema=False)


def page(slug):
    record = next((p for p in PAGES if p[0] == slug), None)
    if record is None:
        raise HTTPException(404, '문서를 찾을 수 없습니다')
    return record


def document_link(href):
    """Keep document navigation local; link repository artifacts to tracked GitHub files."""
    url = urlsplit(href)
    if url.scheme or url.netloc or not url.path:
        return href
    target = (DIRECTORY / url.path).resolve()
    for slug, filename, _ in PAGES:
        if target == DIRECTORY / filename:
            return urlunsplit(('', '', '/guide' if slug == 'index' else '/guide/' + slug,
                               url.query, url.fragment))
    if not target.is_relative_to(ROOT):
        return '#'
    kind = 'tree' if target.is_dir() else 'blob'
    path = quote(target.relative_to(ROOT).as_posix(), safe='/')
    return urlunsplit(('https', 'github.com', f'/yongkyu4803/gnu_10team/{kind}/main/{path}',
                       url.query, url.fragment))


def render(slug):
    _, filename, title = page(slug)
    markdown = MarkdownIt('commonmark', {'html': False}).enable('table')
    tokens = markdown.parse((DIRECTORY / filename).read_text(encoding='utf-8'))
    toc = []
    seen = {}
    for index, token in enumerate(tokens):
        if token.type == 'heading_open':
            text = tokens[index + 1].content
            base = re.sub(r'[^\w\s-]', '', text.lower()).strip().replace(' ', '-') or 'section'
            count = seen.get(base, 0)
            seen[base] = count + 1
            anchor = base + (f'-{count}' if count else '')
            token.attrSet('id', anchor)
            if token.tag == 'h2':
                toc.append((anchor, text))
        for child in token.children or []:
            if child.type == 'link_open':
                child.attrSet('href', document_link(child.attrGet('href') or ''))
    body = markdown.renderer.render(tokens, markdown.options, {})
    navigation = ''.join(
        f'<a href="{"/guide" if key == "index" else "/guide/" + key}"'
        f'{" aria-current=\"page\"" if key == slug else ""}>{escape(label)}</a>'
        for key, _, label in PAGES
    )
    contents = ''.join(f'<a href="#{escape(anchor, quote=True)}">{escape(label)}</a>'
                       for anchor, label in toc)
    position = next(i for i, item in enumerate(PAGES) if item[0] == slug)
    adjacent = []
    for offset, label in ((-1, '이전 문서'), (1, '다음 문서')):
        if 0 <= position + offset < len(PAGES):
            key, _, name = PAGES[position + offset]
            adjacent.append(f'<a href="{"/guide" if key == "index" else "/guide/" + key}">'
                            f'<small>{label}</small><span>{escape(name)}</span></a>')
    return HTMLResponse(f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} · 논문 글쓰기 진단</title>
<link rel="stylesheet" href="/assets/style.css"><link rel="stylesheet" href="/assets/docs.css"></head>
<body class="documentation"><a class="skip-link" href="#document">본문으로 건너뛰기</a>
<header class="appbar"><a class="brand" href="/">논문 글쓰기 진단</a>
<nav class="appnav" aria-label="작업 선택"><a href="/">원고 진단</a><a href="/admin">기준 관리</a><a class="selected" href="/guide" aria-current="page">문서</a></nav></header>
<div class="docs-layout"><aside class="docs-sidebar"><nav class="docs-pages" aria-label="프로젝트 문서"><h2>프로젝트 문서</h2>{navigation}</nav>
<details class="docs-toc" open><summary>이 문서에서</summary><nav aria-label="문서 내 목차">{contents}</nav></details>
<a class="docs-source" href="/guide/{slug}/source">마크다운 다운로드 ↓</a>
<a class="docs-source" href="/docs">API 문서 ↗</a></aside>
<main id="document" class="docs-main" tabindex="-1"><article class="docs-article">{body}</article>
<nav class="docs-adjacent" aria-label="이전·다음 문서">{''.join(adjacent)}</nav></main></div>
</body></html>''')


@router.get('')
def index():
    return render('index')


@router.get('/{slug}/source')
def source(slug: str):
    _, filename, _ = page(slug)
    return FileResponse(DIRECTORY / filename, filename=filename, media_type='text/markdown')


@router.get('/{slug}')
def detail(slug: str):
    return render(slug)
