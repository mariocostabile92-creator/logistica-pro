from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO

import pdfplumber


class PdfReadError(ValueError):
    pass


@dataclass(frozen=True)
class PdfTextDocument:
    pages: tuple[str, ...]

    @property
    def text(self) -> str:
        return "\n".join(self.pages)


@lru_cache(maxsize=8)
def read_pdf_text(content: bytes) -> PdfTextDocument:
    if not content.startswith(b"%PDF"):
        raise PdfReadError("Il contenuto non e un PDF valido.")
    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            if not pdf.pages:
                raise PdfReadError("Il PDF non contiene pagine.")
            pages = tuple(
                (page.extract_text(x_tolerance=3, y_tolerance=3) or "").strip()
                for page in pdf.pages
            )
    except PdfReadError:
        raise
    except Exception as exc:
        raise PdfReadError("Il PDF non e leggibile.") from exc
    if not any(pages):
        raise PdfReadError("Il PDF non contiene testo estraibile.")
    return PdfTextDocument(pages=pages)
