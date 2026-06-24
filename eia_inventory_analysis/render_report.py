"""
Render report/report.md to a polished, self-contained report.html (figures
embedded as base64 -> single shareable file that prints to PDF from any browser)
and a best-effort report.pdf.
"""
import os
import re
import base64
import markdown

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.join(HERE, "report")
MD = os.path.join(REPORT, "report.md")
HTML = os.path.join(REPORT, "report.html")
PDF = os.path.join(REPORT, "report.pdf")

CSS = """
@page { size: A4; margin: 1.6cm; }
* { box-sizing: border-box; }
body { font-family: -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
       color:#1a1a1a; line-height:1.55; max-width:980px; margin:0 auto; padding:32px 28px; }
h1 { font-size:26px; border-bottom:3px solid #1f4e79; padding-bottom:8px; color:#1f4e79; }
h2 { font-size:20px; margin-top:30px; border-bottom:1px solid #d0d7de; padding-bottom:5px; color:#1f4e79; }
h3 { font-size:16px; margin-top:20px; color:#244; }
p, li { font-size:13.5px; }
em { color:#555; }
strong { color:#111; }
hr { border:none; border-top:1px solid #d0d7de; margin:26px 0; }
img { max-width:100%; height:auto; display:block; margin:14px auto; border:1px solid #e2e2e2;
      border-radius:4px; }
table { border-collapse:collapse; width:100%; margin:14px 0; font-size:11.5px; }
th,td { border:1px solid #cbd5e0; padding:5px 8px; text-align:right; }
th { background:#1f4e79; color:#fff; text-align:center; }
td:first-child, th:first-child { text-align:left; }
tr:nth-child(even) td { background:#f4f7fb; }
code { background:#eef1f4; padding:1px 5px; border-radius:3px; font-size:12px; }
blockquote { border-left:4px solid #1f4e79; margin:12px 0; padding:4px 14px; background:#f4f7fb; color:#333; }
.footer { margin-top:34px; font-size:11px; color:#888; border-top:1px solid #d0d7de; padding-top:10px; }
"""


def embed_images(html):
    def repl(m):
        src = m.group(1)
        path = os.path.join(REPORT, src)
        if os.path.exists(path):
            b64 = base64.b64encode(open(path, "rb").read()).decode()
            return f'src="data:image/png;base64,{b64}"'
        return m.group(0)
    return re.sub(r'src="([^"]+)"', repl, html)


def main():
    md_text = open(MD, encoding="utf-8").read()
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists", "attr_list"])
    body_embedded = embed_images(body)
    doc = (f"<!doctype html><html><head><meta charset='utf-8'>"
           f"<title>Crude Inventory Market-Impact Framework</title>"
           f"<style>{CSS}</style></head><body>{body_embedded}"
           f"<div class='footer'>Systematic EIA Crude-Inventory Framework &middot; "
           f"generated from report.md &middot; figures embedded.</div></body></html>")
    with open(HTML, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"wrote {HTML}  ({os.path.getsize(HTML)//1024} KB, self-contained)")

    # best-effort PDF (xhtml2pdf; CSS support is limited but produces a shareable PDF)
    try:
        from xhtml2pdf import pisa
        with open(PDF, "wb") as out:
            status = pisa.CreatePDF(doc, dest=out)
        if status.err:
            print("  PDF: completed with warnings (xhtml2pdf has limited CSS support)")
        print(f"wrote {PDF}  ({os.path.getsize(PDF)//1024} KB)")
    except Exception as e:
        print(f"  PDF skipped ({e}). Open report.html in a browser and Print -> Save as PDF.")


if __name__ == "__main__":
    main()
