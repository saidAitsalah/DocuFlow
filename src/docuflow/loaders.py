from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

MIN_TEXT_CHARS = 50


def load_pdf(path: str | Path) -> Document:
    """Merge all pages into one Document; keep the file name for citations."""
    pages = PyPDFLoader(str(path)).load()
    text = "\n\n".join(p.page_content for p in pages)
    return Document(
        page_content=text,
        metadata={
            "source": Path(path).name,
            "pages": len(pages),
            # Scanned PDFs have no text layer
            "needs_ocr": len(text.strip()) < MIN_TEXT_CHARS,
        },
    )