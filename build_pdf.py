#!/usr/bin/env python3
"""
Build the E4B + Serena setup guide PDF with properly wrapped table cells.
Uses Paragraph objects in table cells so text wraps within column widths.
"""
import json
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether
)
from reportlab.lib import colors
from reportlab.lib.units import mm

SPEC_FILE = os.path.join(os.path.dirname(__file__), "pdf_spec.json")
OUT_FILE = os.path.join(os.path.dirname(__file__), "e4b-serena-setup-guide.pdf")

PAGE_SIZE = A4
MARGIN = 20 * mm
CONTENT_WIDTH = PAGE_SIZE[0] - 2 * MARGIN  # ~555pt for A4

styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    'TitleStyle', parent=styles['Title'],
    fontSize=22, leading=26, spaceAfter=6, textColor=colors.HexColor('#003366')
)
h1_style = ParagraphStyle(
    'H1Style', parent=styles['Heading1'],
    fontSize=16, leading=20, spaceBefore=16, spaceAfter=8,
    textColor=colors.HexColor('#003366')
)
h2_style = ParagraphStyle(
    'H2Style', parent=styles['Heading2'],
    fontSize=13, leading=16, spaceBefore=10, spaceAfter=4,
    textColor=colors.HexColor('#004488')
)
body_style = ParagraphStyle(
    'BodyStyle', parent=styles['BodyText'],
    fontSize=10, leading=13, spaceBefore=0, spaceAfter=2,
    fontName='Helvetica', wordWrap='CJK'
)
mono_style = ParagraphStyle(
    'MonoStyle', parent=styles['BodyText'],
    fontSize=8, leading=10, spaceBefore=0, spaceAfter=2,
    fontName='Courier', textColor=colors.HexColor('#333333'),
    wordWrap='CJK'  # force wrapping for long commands
)
cell_style = ParagraphStyle(
    'CellStyle', parent=styles['BodyText'],
    fontSize=8, leading=10, spaceBefore=0, spaceAfter=0,
    fontName='Helvetica'
)
cell_mono_style = ParagraphStyle(
    'CellMonoStyle', parent=styles['BodyText'],
    fontSize=7.5, leading=9.5, spaceBefore=0, spaceAfter=0,
    fontName='Courier', textColor=colors.HexColor('#333333')
)
header_cell_style = ParagraphStyle(
    'HeaderCellStyle', parent=styles['BodyText'],
    fontSize=8.5, leading=10, spaceBefore=0, spaceAfter=0,
    fontName='Helvetica-Bold', textColor=colors.black
)


def make_wrapped_table(el):
    """Build a table with Paragraph-wrapped cells that fit within page width."""
    headers = el.get("headers", [])
    rows = el.get("rows", [])
    has_header = bool(headers)
    num_cols = len(headers) if has_header else (len(rows[0]) if rows else 0)
    if num_cols == 0:
        return Spacer(1, 1)

    # Determine column widths based on content type
    # Slightly under 100% to keep grid borders inside the content area
    w_frac = 0.93  # keep grid borders well inside content area
    if num_cols == 4:
        col_widths = [CONTENT_WIDTH * 0.24 * w_frac, CONTENT_WIDTH * 0.16 * w_frac, CONTENT_WIDTH * 0.12 * w_frac, CONTENT_WIDTH * 0.48 * w_frac]
    elif num_cols == 3:
        col_widths = [CONTENT_WIDTH * 0.30 * w_frac, CONTENT_WIDTH * 0.18 * w_frac, CONTENT_WIDTH * 0.52 * w_frac]
    elif num_cols == 2:
        col_widths = [CONTENT_WIDTH * 0.35 * w_frac, CONTENT_WIDTH * 0.65 * w_frac]
    elif num_cols == 5:
        col_widths = [CONTENT_WIDTH * 0.22 * w_frac, CONTENT_WIDTH * 0.13 * w_frac, CONTENT_WIDTH * 0.15 * w_frac, CONTENT_WIDTH * 0.13 * w_frac, CONTENT_WIDTH * 0.37 * w_frac]
    else:
        col_widths = [CONTENT_WIDTH * w_frac / num_cols] * num_cols

    # Build all rows with wrapped cells
    all_rows = []
    if has_header:
        header_row = [Paragraph(str(h), header_cell_style) for h in headers]
        all_rows.append(header_row)

    for row in rows:
        wrapped_row = []
        for col_idx, cell in enumerate(row):
            text = str(cell) if cell else ""
            # Use monospace for cells that look like commands/flags
            if col_idx == 0 and (text.startswith("-") or text.startswith("--") or
                                 "GGML" in text or "setsid" in text or "/" in text or
                                 text in ["MAX_TOKENS", "TEMPERATURE", "TOP_P", "MAX_TURNS",
                                          "LLM_BASE_URL", "LLM_MODEL", "httpx timeout",
                                          "max_tool_result_chars", "tool_choice",
                                          "Serena context", "tool_timeout", "log_level",
                                          "language_backend", "gui_log_window",
                                          "web_dashboard", "web_dashboard_open_on_launch",
                                          "--context"]):
                wrapped_row.append(Paragraph(text, cell_mono_style))
            else:
                wrapped_row.append(Paragraph(text, cell_style))
        all_rows.append(wrapped_row)

    table = Table(all_rows, colWidths=col_widths, repeatRows=1 if has_header else 0)

    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if has_header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor('#D0E0F0')))
        style.append(("FONTNAME", (0, 0), (-1, 0), 'Helvetica-Bold'))
    table.setStyle(TableStyle(style))

    return table


def build_story(spec):
    """Convert the JSON spec into reportlab flowables."""
    story = []
    elements = spec.get("elements", [])

    # Title block
    if spec.get("title"):
        story.append(Paragraph(spec["title"], title_style))
    if spec.get("author"):
        story.append(Paragraph(f"Author: {spec['author']}", body_style))
    if spec.get("subject"):
        story.append(Paragraph(spec["subject"], body_style))
    story.append(Spacer(1, 6))

    for el in elements:
        el_type = el.get("type", "")

        if el_type == "heading":
            level = el.get("level", 1)
            text = el.get("text", "")
            if level == 1:
                story.append(Paragraph(text, h1_style))
            elif level == 2:
                story.append(Paragraph(text, h2_style))
            else:
                story.append(Paragraph(text, h2_style))

        elif el_type == "paragraph":
            text = el.get("text", "")
            # Detect monospace content (commands, code)
            if (text.startswith("GGML_") or text.startswith("python3") or
                text.startswith("pip ") or text.startswith("which ") or
                text.startswith("curl ") or text.startswith("sudo ") or
                text.startswith("cd ") or text.startswith("./") or
                text.startswith("setsid") or text.startswith("for ") or
                text.startswith("  -") or text.startswith("  --") or
                text.startswith("  ~") or text.startswith("  python") or
                text.startswith("  curl") or text.startswith("  sleep") or
                text.startswith("  break") or text.startswith("  done") or
                text.startswith("  args:") or text.startswith("  command:") or
                text.startswith("  #") or
                text.startswith("Or use") or
                text.startswith("Check generation") or
                text.startswith("Note:") or
                "agent_config.yaml" in text and "Edit" in text):
                story.append(Paragraph(text, mono_style))
            else:
                story.append(Paragraph(text, body_style))

        elif el_type == "table":
            story.append(Spacer(1, 4))
            story.append(make_wrapped_table(el))
            story.append(Spacer(1, 4))

        elif el_type == "pagebreak":
            story.append(PageBreak())

    return story


def add_page_number(canvas, doc):
    """Add page numbers at the bottom."""
    canvas.saveState()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.grey)
    page_num = canvas.getPageNumber()
    canvas.drawCentredString(PAGE_SIZE[0] / 2, 12 * mm, f"Page {page_num}")
    canvas.restoreState()


def main():
    with open(SPEC_FILE) as f:
        spec = json.load(f)

    doc = SimpleDocTemplate(
        OUT_FILE,
        pagesize=PAGE_SIZE,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN + 8 * mm,
        title=spec.get("title", ""),
        author=spec.get("author", ""),
        subject=spec.get("subject", ""),
        keywords=spec.get("keywords", ""),
    )

    story = build_story(spec)
    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f"PDF created: {OUT_FILE} ({len(story)} flowables)")


if __name__ == "__main__":
    main()