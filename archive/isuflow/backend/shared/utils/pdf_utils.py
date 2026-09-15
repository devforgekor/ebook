import io
import re
import traceback
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image
import fitz  # PyMuPDF (for reliable PDF → image)
import imghdr


# ✅ 1) PDF 안전성 검사
# 문서 정책 3.11 · 보안 정책 기반
def validate_pdf_safety(pdf_bytes: bytes):
    """
    수행 내용:
    - MIME 위장 검사
    - PDF Header 검사 (%PDF-)
    - JavaScript 삽입 검사 (/JS, /JavaScript)
    - 비정상 Stream / Encryption 검사
    """
    # ✅ 1) header 검사 (PDF signature)
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("Invalid PDF format: missing %PDF header")

    # ✅ 2) MIME 위장 검사
    # JPEG 등으로 위장된 경우 방지
    if imghdr.what(None, pdf_bytes):
        raise ValueError("PDF disguised as image detected")

    # ✅ 3) JavaScript 삽입 여부 검사
    # 공격 코드 예: /JS(), /JavaScript
    if re.search(rb"/JS|/JavaScript", pdf_bytes):
        raise ValueError("PDF contains JavaScript. Potentially dangerous.")

    # ✅ 4) PyPDF2 구조 검사
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))

        # 암호화 PDF는 거부
        if reader.is_encrypted:
            raise ValueError("Encrypted PDF is not allowed.")
    except Exception:
        print("🔥 PDF structure validation error:")
        print(traceback.format_exc())
        raise ValueError("PDF structure is invalid or corrupted.")


# ✅ 2) PDF 메타데이터 삽입 (비식별 ID만)
# 문서 정책 3.2
def insert_pdf_metadata(pdf_bytes: bytes, person_id: str, record_key: str) -> bytes:
    """
    삽입되는 key:
      - person_id
      - record_key

    PII(name, yymmdd, org 등) 절대 금지
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()

    # 페이지 복사
    for page in reader.pages:
        writer.add_page(page)

    # ✅ 비식별 메타데이터 삽입
    writer.add_metadata({
        "/person_id": person_id,
        "/record_key": record_key
    })

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


# ✅ 3) PDF 첫 페이지 → 이미지(Pillow) 변환
# processPdf에서 WebP 변환 전에 반드시 호출
def pdf_first_page_to_image(pdf_bytes: bytes) -> Image.Image:
    """
    PyMuPDF(fitz)를 사용하여 PDF의 첫 페이지를
    고해상도 이미지로 렌더링한 뒤 Pillow Image 객체로 반환.
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc.load_page(0)

        # 고해상도 렌더링 (2x scaling)
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return img

    except Exception:
        print("🔥 pdf_first_page_to_image error:")
        print(traceback.format_exc())
        raise ValueError("PDF rendering failed (first page).")
    
