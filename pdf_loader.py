"""Phase 1: page-aware PDF text extraction (PyMuPDF), with an OCR fallback
for scanned / image-only PDFs."""

import pymupdf

# OCR is attempted only for a PDF whose pages carry no text layer (a scan),
# and is bounded so it can't turn one upload into minutes of CPU: at most this
# many pages, rendered at this zoom (~144 DPI, enough for clean scans).
OCR_MAX_PAGES = 30
OCR_ZOOM = 2.0
OCR_MIN_CHARS = 12  # a page is "empty" if the text layer has fewer than this


def load_pdf_pages(pdf_bytes: bytes) -> list[tuple[int, str]]:
    """Extract text per page from PDF bytes.

    Returns a list of (page_number, page_text) pairs, 1-indexed. Pages with a
    text layer are read directly; if the whole document has no text layer (a
    scan), each page is OCR'd instead, up to OCR_MAX_PAGES. Returns an empty
    list for an invalid, corrupt, or fully-empty PDF instead of raising.
    """
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            pages = [
                (i + 1, text)
                for i in range(doc.page_count)
                if (text := doc[i].get_text().strip())
            ]
            if pages:
                return pages
            # No text layer anywhere: treat it as a scan and OCR the pages.
            return _ocr_pages(doc)
    except Exception:
        return []


def _ocr_pages(doc) -> list[tuple[int, str]]:
    """OCR the first OCR_MAX_PAGES pages of a scanned document. Returns []
    (so the caller reports an unreadable PDF) if OCR isn't available or finds
    nothing."""
    try:
        import pytesseract
        from PIL import Image
    except Exception:
        return []

    matrix = pymupdf.Matrix(OCR_ZOOM, OCR_ZOOM)
    pages = []
    for i in range(min(doc.page_count, OCR_MAX_PAGES)):
        try:
            pixmap = doc[i].get_pixmap(matrix=matrix)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            text = pytesseract.image_to_string(image).strip()
        except pytesseract.TesseractNotFoundError:
            return []  # the tesseract binary isn't installed
        except Exception:
            continue  # skip a page that fails, keep the rest
        if len(text) >= OCR_MIN_CHARS:
            pages.append((i + 1, text))
    return pages
