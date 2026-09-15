import io
from PIL import Image
from azure.storage.blob import BlobClient


# ✅ 1) Pillow Image → WebP 변환 (bytes 반환)
def _image_to_webp_bytes(img: Image.Image, quality: int = 80) -> bytes:
    """
    공통 WebP 변환 함수.
    processPdf 및 preview API에서 사용.
    """
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=quality, method=6)
    return buf.getvalue()


# ✅ 2) 운영용 WebP 저장 (optimized-copies/)
def upload_webp_optimized(blob: BlobClient, img: Image.Image, quality: int = 80):
    """
    운영용 WebP: processPdf가 만든 '정규본' WebP.
    optimized-copies 컨테이너에 저장.
    """
    data = _image_to_webp_bytes(img, quality=quality)
    blob.upload_blob(data, overwrite=True)
    return True


# ✅ 3) 프리뷰용 WebP 저장 (temp/)
def upload_temp_webp(blob: BlobClient, img: Image.Image):
    """
    preview API에서 사용하는 임시 WebP용.
    품질은 높이되 capacity는 낮도록 70 적용.
    """
    data = _image_to_webp_bytes(img, quality=70)
    blob.upload_blob(data, overwrite=True)
    return True


# ✅ 4) 아카이빙용 WebP (흑백 + 저용량)
def convert_to_archive_webp(img: Image.Image) -> bytes:
    """
    아카이브 정책:
      - WebP → 흑백(grayscale)
      - 파일 크기 최소화
    """
    gray = img.convert("L")
    return _image_to_webp_bytes(gray, quality=50)


