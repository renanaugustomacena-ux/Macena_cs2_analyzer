#!/usr/bin/env python3
"""
Render Mermaid diagrams to SVG and generate dark-themed PDFs
from the Book-Coach-{1,2,3}.md documentation files.

Usage:
    source /home/renan/.venvs/cs2analyzer/bin/activate
    python docs/generate_zh_pdfs.py
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

MMDC = Path(os.environ.get("MMDC_PATH", shutil.which("mmdc") or "mmdc"))
DOCS_DIR = Path(os.environ.get("DOCS_DIR", Path(__file__).parent.resolve()))
OUT_DIR = DOCS_DIR / "pdf_zh_output"

PUPPETEER_CFG = {
    "executablePath": "/usr/bin/google-chrome-stable",
    "args": ["--no-sandbox", "--disable-gpu"],
}

FONT_REGULAR = str(Path.home() / ".local/share/fonts/atkinson/AtkinsonHyperlegible-Regular.ttf")
FONT_BOLD = str(Path.home() / ".local/share/fonts/atkinson/AtkinsonHyperlegible-Bold.ttf")
FONT_ITALIC = str(Path.home() / ".local/share/fonts/atkinson/AtkinsonHyperlegible-Italic.ttf")
FONT_BOLD_ITALIC = str(Path.home() / ".local/share/fonts/atkinson/AtkinsonHyperlegible-BoldItalic.ttf")

CSS = f"""
@font-face {{
    font-family: 'Atkinson';
    src: url('{FONT_REGULAR}') format('truetype');
    font-weight: normal;
    font-style: normal;
}}
@font-face {{
    font-family: 'Atkinson';
    src: url('{FONT_BOLD}') format('truetype');
    font-weight: bold;
    font-style: normal;
}}
@font-face {{
    font-family: 'Atkinson';
    src: url('{FONT_ITALIC}') format('truetype');
    font-weight: normal;
    font-style: italic;
}}
@font-face {{
    font-family: 'Atkinson';
    src: url('{FONT_BOLD_ITALIC}') format('truetype');
    font-weight: bold;
    font-style: italic;
}}
@font-face {{
    font-family: 'NotoTC';
    src: url('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc') format('truetype');
    font-weight: normal;
}}
@font-face {{
    font-family: 'NotoTC';
    src: url('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc') format('truetype');
    font-weight: bold;
}}
@page {{ size: A4; margin: 18mm 15mm 18mm 15mm; background: #030303; }}
body {{
    font-family: 'Atkinson', 'NotoTC', sans-serif;
    font-size: 10pt;
    line-height: 1.7;
    color: #e8e8e8;
    background: #030303;
}}
h1 {{ font-size: 20pt; color: #e0eaff; border-bottom: 3px solid rgba(100, 160, 255, 0.35); padding-bottom: 0.3em; margin-top: 1.2em; }}
h2 {{ font-size: 15pt; color: #dce6f8; border-bottom: 1.5px solid rgba(255, 255, 255, 0.15); padding-bottom: 0.2em; margin-top: 1em; }}
h3 {{ font-size: 12pt; color: #d4e0f4; margin-top: 0.8em; }}
h4 {{ font-size: 11pt; color: #ccd8ee; margin-top: 0.7em; }}
code {{
    font-family: 'Courier New', monospace;
    background: #1a1a1a;
    border-radius: 3px;
    padding: 1px 4px;
    font-size: 8.5pt;
    color: #c8d8e8;
}}
pre {{
    font-family: 'Courier New', monospace;
    background: #111111;
    border: 1px solid #2a2a2a;
    border-radius: 4px;
    padding: 8px;
    font-size: 8pt;
    overflow: auto;
    page-break-inside: avoid;
    color: #c8d8e8;
}}
blockquote {{
    background: #0c0c14;
    border-left: 4px solid rgba(100, 160, 255, 0.4);
    margin: 0.8em 0;
    padding: 0.6em 1em;
    color: #c0c8d8;
    font-size: 9.5pt;
    page-break-inside: avoid;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 0.7em 0;
    font-size: 8.5pt;
    page-break-inside: avoid;
}}
th {{
    background: #1a2a3a;
    color: #e0eaff;
    padding: 5px 8px;
    text-align: left;
    border: 1px solid #2a3a4a;
}}
td {{ border: 1px solid #222; padding: 4px 8px; color: #d0d0d0; }}
tr:nth-child(even) {{ background: #0a0a0a; }}
tr:nth-child(odd) {{ background: #060606; }}
a {{ color: #7ab0f0; }}
img.diagram {{
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1em auto;
    page-break-inside: avoid;
}}
.diagram-fallback {{
    background: #111;
    border: 1px dashed #444;
    padding: 0.5em;
    font-size: 7.5pt;
    font-family: monospace;
    white-space: pre;
    page-break-inside: avoid;
    color: #aaa;
}}
hr {{ border: 0; border-top: 1px solid #222; margin: 1.5em 0; }}
strong {{ color: #f0f0f0; }}
em {{ color: #ddd; }}
"""


def render_mermaid(mermaid_code: str, svg_path: Path) -> bool:
    """Render one Mermaid diagram to SVG using mmdc."""
    mmd_tmp = None
    cfg_tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mmd', delete=False, encoding='utf-8') as f:
            f.write(mermaid_code)
            mmd_tmp = f.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(PUPPETEER_CFG, f)
            cfg_tmp = f.name
        r = subprocess.run(
            [str(MMDC), '-i', mmd_tmp, '-o', str(svg_path),
             '--width', '750', '--backgroundColor', 'transparent',
             '-p', cfg_tmp],
            capture_output=True, text=True, timeout=45
        )
        return r.returncode == 0 and svg_path.exists()
    except Exception as exc:
        print(f"  [mermaid error] {exc}")
        return False
    finally:
        for p in (mmd_tmp, cfg_tmp):
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass


def process_markdown(md_path: Path, out_dir: Path) -> str:
    """
    Replace ```mermaid...``` blocks with rendered SVG <img> tags.
    Returns HTML string ready for weasyprint.
    """
    import markdown as md_lib

    text = md_path.read_text(encoding='utf-8')
    counter = [0]

    mermaid_re = re.compile(r'```mermaid\r?\n(.*?)\r?\n```', re.DOTALL)

    def replace(m):
        counter[0] += 1
        code = m.group(1)
        svg_name = f"{md_path.stem}_diag_{counter[0]:03d}.svg"
        svg_path = out_dir / svg_name
        ok = render_mermaid(code, svg_path)
        if ok:
            print(f"  diagram {counter[0]:3d} → {svg_name}")
            return f'<img class="diagram" src="{svg_name}" alt="圖表 {counter[0]}" />'
        else:
            print(f"  diagram {counter[0]:3d} → FAILED (showing as code)")
            return f'<div class="diagram-fallback">{code}</div>'

    processed = mermaid_re.sub(replace, text)

    converter = md_lib.Markdown(extensions=[
        'tables', 'fenced_code', 'toc', 'nl2br',
        'markdown.extensions.codehilite',
    ], extension_configs={
        'codehilite': {'guess_lang': False, 'noclasses': True},
    })
    return converter.convert(processed)


def to_pdf(html_body: str, out_pdf: Path, title: str, part_num: int):
    """Wrap HTML body in a full page and render to PDF with weasyprint."""
    from weasyprint import HTML as WH

    full_html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>{CSS}</style>
</head>
<body>
<div style="text-align:center;margin-bottom:2em;">
  <p style="font-size:9pt;color:#555;">Macena CS2 Analyzer — Part {part_num}</p>
</div>
{html_body}
</body>
</html>"""

    WH(string=full_html, base_url=str(out_pdf.parent)).write_pdf(str(out_pdf))
    print(f"  ✓ PDF written: {out_pdf.name} ({out_pdf.stat().st_size // 1024} KB)")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    files = [
        ("Book-Coach-1.md", "Ultimate CS2 Coach — Part 1", 1),
        ("Book-Coach-2.md", "Ultimate CS2 Coach — Part 2", 2),
        ("Book-Coach-3.md", "Ultimate CS2 Coach — Part 3", 3),
    ]

    for fname, title, part_num in files:
        src = DOCS_DIR / fname
        if not src.exists():
            print(f"[SKIP] {fname} — file not found.")
            continue
        print(f"\n[{part_num}/3] Processing {fname} ...")
        html = process_markdown(src, OUT_DIR)
        pdf_out = OUT_DIR / fname.replace('.md', '.pdf')
        to_pdf(html, pdf_out, title, part_num)

    print("\nDone. PDFs in:", OUT_DIR)


if __name__ == "__main__":
    main()
