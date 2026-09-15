from azure.storage.blob import BlobClient


# ✅ 1) Blob Tags 설정 (overwrites=True 유지)
def set_blob_tags_optimized(blob: BlobClient, tags: dict):
    """
    BlobClient 객체에 대해 Tag를 설정한다.
    - optimized-copies (PDF/WebP)에서 공통 사용
    - processPdf가 호출
    - 9개 Tag 정책 지원

    tags 예:
    {
        "lookup_key": person_id,
        "person_id": person_id,
        "record_key": record_key,
        "year": year,
        "hours": hours,
        "org_key": org,
        "position_key": position,
        "title_key": title,
        "cert_number": record_key
    }
    """
    try:
        # Azure SDK는 dict[str,str] 요구
        str_tags = {str(k): str(v) for k, v in tags.items()}
        blob.set_blob_tags(str_tags)
        return True
    except Exception as e:
        print("🔥 Blob Tag 설정 중 오류:")
        print(e)
        return False


# ✅ 2) Blob Tags 조회
def get_blob_tags(blob: BlobClient) -> dict:
    """
    Blob에 설정된 태그를 반환한다.
    """
    try:
        return blob.get_blob_tags()
    except Exception as e:
        print("🔥 Blob Tag 조회 오류:")
        print(e)
        return {}


# ✅ 3) 특정 태그 값 한 개 가져오기 (편의 함수)
def get_blob_tag(blob: BlobClient, key: str):
    """
    특정 key의 Tag 값만 반환.
    """
    try:
        tags = blob.get_blob_tags()
        return tags.get(key)
    except Exception as e:
        print("🔥 Blob Tag 특정 키 조회 오류:")
        print(e)
        return None
    
