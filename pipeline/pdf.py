import pymupdf


def render_pages(pdf_bytes: bytes, dpi: int = 150, quality: int = 85):
    """Return list of (page_no 1-based, jpeg bytes)."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    out = []
    for i, page in enumerate(doc, 1):
        pix = page.get_pixmap(dpi=dpi)
        out.append((i, pix.tobytes("jpeg", jpg_quality=quality)))
    return out
