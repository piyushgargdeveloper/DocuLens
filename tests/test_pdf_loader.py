from pdf_loader import load_pdf_pages


def test_valid_pdf_extracts_all_pages_with_correct_numbering(sample_pdf_bytes):
    pages = load_pdf_pages(sample_pdf_bytes)
    assert [p for p, _ in pages] == [1, 2, 3, 4]
    assert "Solar System" in pages[0][1]


def test_invalid_pdf_bytes_return_empty_list():
    assert load_pdf_pages(b"this is not a pdf") == []


def test_empty_bytes_return_empty_list():
    assert load_pdf_pages(b"") == []


def test_scanned_pdf_falls_back_to_ocr(monkeypatch):
    # A PDF whose pages have no text layer is OCR'd. tesseract is mocked so the
    # test needs no binary; this checks the fallback path is taken and bounded.
    import pymupdf

    import pdf_loader

    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page()  # blank pages: no text layer
    pdf_bytes = doc.tobytes()
    doc.close()

    # Provide a fake pytesseract + PIL so the OCR branch runs deterministically.
    import types

    fake_tess = types.SimpleNamespace(
        image_to_string=lambda img: "Recovered scanned line of text",
        TesseractNotFoundError=RuntimeError,
    )
    fake_pil = types.SimpleNamespace(Image=types.SimpleNamespace(frombytes=lambda *a, **k: object()))
    monkeypatch.setitem(__import__("sys").modules, "pytesseract", fake_tess)
    monkeypatch.setitem(__import__("sys").modules, "PIL", fake_pil)

    pages = pdf_loader.load_pdf_pages(pdf_bytes)
    assert [p for p, _ in pages] == [1, 2, 3]
    assert all("Recovered scanned line" in t for _, t in pages)


def test_ocr_is_bounded_to_max_pages(monkeypatch):
    import types

    import pymupdf

    import pdf_loader

    doc = pymupdf.open()
    for _ in range(pdf_loader.OCR_MAX_PAGES + 5):
        doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()

    fake_tess = types.SimpleNamespace(
        image_to_string=lambda img: "a readable line of text", TesseractNotFoundError=RuntimeError
    )
    fake_pil = types.SimpleNamespace(Image=types.SimpleNamespace(frombytes=lambda *a, **k: object()))
    monkeypatch.setitem(__import__("sys").modules, "pytesseract", fake_tess)
    monkeypatch.setitem(__import__("sys").modules, "PIL", fake_pil)

    pages = pdf_loader.load_pdf_pages(pdf_bytes)
    assert len(pages) == pdf_loader.OCR_MAX_PAGES


def test_pdf_with_a_text_layer_never_triggers_ocr(monkeypatch, sample_pdf_bytes):
    import pdf_loader

    def boom(*a, **k):
        raise AssertionError("OCR must not run when a text layer exists")

    monkeypatch.setattr(pdf_loader, "_ocr_pages", boom)
    pages = pdf_loader.load_pdf_pages(sample_pdf_bytes)
    assert len(pages) == 4
