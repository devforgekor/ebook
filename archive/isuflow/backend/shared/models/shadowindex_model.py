class ShadowIndexEntry:
    """
    ShadowIndex 테이블의 Row를 표현하는 모델 클래스.
    RowKey = record_key
    PartitionKey = person_id

    필드 (TableEntity 기반):
      - person_id
      - record_key
      - year
      - title_key
      - hours
      - org_key
      - position_key
      - cert_number
      - blob_path
    """

    def __init__(self,
                 person_id: str,
                 record_key: str,
                 year: str,
                 title_key: str,
                 hours: str,
                 org_key: str,
                 cert_number: str,
                 blob_path: str,
                 position_key: str = ""):
        self.person_id = person_id
        self.record_key = record_key
        self.year = year
        self.title_key = title_key
        self.hours = hours
        self.org_key = org_key
        self.position_key = position_key
        self.cert_number = cert_number
        self.blob_path = blob_path

    @staticmethod
    def from_entity(e):
        """Azure Table Entity → ShadowIndexEntry"""
        return ShadowIndexEntry(
            person_id=e["PartitionKey"],
            record_key=e["RowKey"],
            year=e.get("year", ""),
            title_key=e.get("title_key", ""),
            hours=e.get("hours", ""),
            org_key=e.get("org_key", ""),
            position_key=e.get("position_key", ""),
            cert_number=e.get("cert_number", ""),
            blob_path=e.get("blob_path", "")
        )

    def to_entity(self):
        """ShadowIndexEntry → Azure Table Entity"""
        return {
            "PartitionKey": self.person_id,
            "RowKey": self.record_key,
            "year": self.year,
            "title_key": self.title_key,
            "hours": self.hours,
            "org_key": self.org_key,
            "position_key": self.position_key,
            "cert_number": self.cert_number,
            "blob_path": self.blob_path
        }

    def to_history_dict(self):
        """
        checkList API의 히스토리 응답용
        """
        return {
            "submitted_at": self.record_key.split("_")[-1],
            "title": self.title_key,
            "hours": self.hours
        }
    
    