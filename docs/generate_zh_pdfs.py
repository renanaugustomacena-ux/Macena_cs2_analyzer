#!/usr/bin/env python3
"""
Render Mermaid diagrams to SVG and generate Traditional Chinese PDFs
from the AI-cs2-coach-part*-ZH.md translation files.

Usage:
    source /home/renan/.venvs/cs2analyzer/bin/activate
    python docs/generate_zh_pdfs.py
"""
import os
import re
import subprocess
import tempfile
from pathlib import Path

MMDC = Path("/home/renan/npm-global/node_modules/.bin/mmdc")
DOCS_DIR = Path("/media/renan/SSD Portable/Counter-Strike-coach-AI/Counter-Strike-coach-AI-main/docs")
OUT_DIR = DOCS_DIR / "pdf_zh_output"
FONT_SANS = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_SANS_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

CSS = """
@font-face {
    font-family: 'NotoTC';
    src: url('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc') format('truetype');
    font-weight: normal;
}
@font-face {
    font-family: 'NotoTC';
    src: url('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc') format('truetype');
    font-weight: bold;
}
@page { size: A4; margin: 18mm 15mm 18mm 15mm; }
body {
    font-family: 'NotoTC', sans-serif;
    font-size: 10pt;
    line-height: 1.7;
    color: #1a1a1a;
}
h1 { font-size: 20pt; color: #0d2137; border-bottom: 3px solid #4a9eff; padding-bottom: 0.3em; margin-top: 1.2em; }
h2 { font-size: 15pt; color: #0d2137; border-bottom: 1.5px solid #aaa; padding-bottom: 0.2em; margin-top: 1em; }
h3 { font-size: 12pt; color: #1a3a5c; margin-top: 0.8em; }
h4 { font-size: 11pt; color: #2c4870; margin-top: 0.7em; }
code {
    font-family: 'Courier New', monospace;
    background: #f4f4f4;
    border-radius: 3px;
    padding: 1px 4px;
    font-size: 8.5pt;
}
pre {
    font-family: 'Courier New', monospace;
    background: #f4f4f4;
    border: 1px solid #ddd;
    border-radius: 4px;
    padding: 8px;
    font-size: 8pt;
    overflow: auto;
    page-break-inside: avoid;
}
blockquote {
    background: #eef4ff;
    border-left: 4px solid #4a9eff;
    margin: 0.8em 0;
    padding: 0.6em 1em;
    color: #333;
    font-size: 9.5pt;
    page-break-inside: avoid;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 0.7em 0;
    font-size: 8.5pt;
    page-break-inside: avoid;
}
th {
    background: #4a9eff;
    color: white;
    padding: 5px 8px;
    text-align: left;
}
td { border: 1px solid #ccc; padding: 4px 8px; }
tr:nth-child(even) { background: #f8f9fa; }
img.diagram {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1em auto;
    page-break-inside: avoid;
}
.diagram-fallback {
    background: #fff8e1;
    border: 1px dashed #f0a500;
    padding: 0.5em;
    font-size: 7.5pt;
    font-family: monospace;
    white-space: pre;
    page-break-inside: avoid;
}
hr { border: 0; border-top: 1px solid #ccc; margin: 1.5em 0; }
"""


def render_mermaid(mermaid_code: str, svg_path: Path) -> bool:
    """Render one Mermaid diagram to SVG using mmdc."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.mmd', delete=False, encoding='utf-8') as f:
        f.write(mermaid_code)
        tmp = f.name
    try:
        r = subprocess.run(
            [str(MMDC), '-i', tmp, '-o', str(svg_path),
             '--width', '750', '--backgroundColor', 'white'],
            capture_output=True, text=True, timeout=45
        )
        return r.returncode == 0 and svg_path.exists()
    except Exception as exc:
        print(f"  [mermaid error] {exc}")
        return False
    finally:
        try:
            os.unlink(tmp)
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

    part_label = f"第{part_num}部分"
    full_html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>{CSS}</style>
</head>
<body>
<div style="text-align:center;margin-bottom:2em;">
  <p style="font-size:9pt;color:#888;">Macena CS2 Analyzer — 完整技術文件 {part_label}</p>
</div>
{html_body}
</body>
</html>"""

    WH(string=full_html, base_url=str(out_pdf.parent)).write_pdf(str(out_pdf))
    print(f"  ✓ PDF written: {out_pdf.name} ({out_pdf.stat().st_size // 1024} KB)")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    files = [
        ("AI-cs2-coach-part1-ZH.md", "CS2 AI 教練系統：完整技術指南 — 第一部分", 1),
        ("AI-cs2-coach-part2-ZH.md", "CS2 AI 教練系統：完整技術指南 — 第二部分", 2),
        ("AI-cs2-coach-part3-ZH.md", "CS2 AI 教練系統：完整技術指南 — 第三部分", 3),
    ]

    for fname, title, part_num in files:
        src = DOCS_DIR / fname
        if not src.exists():
            print(f"[SKIP] {fname} — file not found. Please create the translation first.")
            continue
        print(f"\n[{part_num}/3] Processing {fname} ...")
        html = process_markdown(src, OUT_DIR)
        pdf_out = OUT_DIR / fname.replace('-ZH.md', '-ZH.pdf')
        to_pdf(html, pdf_out, title, part_num)

    print("\nDone. PDFs in:", OUT_DIR)


if __name__ == "__main__":
    main()
