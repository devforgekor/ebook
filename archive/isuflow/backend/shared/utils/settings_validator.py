import re
from datetime import datetime


class SettingsValidator:
    """
    updateSchedule() 입력(body)를 검증하는 전용 Validator.

    다음 항목 전체 검사:
      - HOLIDAY_RECUR
      - HOLIDAY_CUSTOM
      - HOLIDAY_SEOL
      - HOLIDAY_CHUSEOK
      - BREAK_SUMMER
      - BREAK_WINTER
      - BREAK_SHORT (여러개)
      - START_TIME / END_TIME (optional)

    실패 시 ValueError 발생 → updateSchedule API에서 bad_request 처리
    """

    # ------------------------------------------------------------
    # ✅ 기본 포맷 검사 정규식
    # ------------------------------------------------------------
    MD_PATTERN = re.compile(r"^\d{2}\.\d{2}$")            # MM.DD
    YMD_PATTERN = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")     # YYYY.MM.DD
    RECUR_PATTERN = re.compile(r"^\d{2}-\d{2}$")           # MM-DD

    # ------------------------------------------------------------
    # ✅ 공통 유틸
    # ------------------------------------------------------------
    @staticmethod
    def _validate_md(md: str):
        """MM.DD 형식 검사"""
        if not SettingsValidator.MD_PATTERN.match(md):
            raise ValueError(f"잘못된 날짜 형식입니다: {md} (MM.DD 필요)")

    @staticmethod
    def _validate_ymd(ymd: str):
        """YYYY.MM.DD 형식 검사"""
        if not SettingsValidator.YMD_PATTERN.match(ymd):
            raise ValueError(f"잘못된 날짜 형식입니다: {ymd} (YYYY.MM.DD 필요)")

    @staticmethod
    def _validate_recur(md: str):
        """MM-DD recur 공휴일 형식 검사"""
        if not SettingsValidator.RECUR_PATTERN.match(md):
            raise ValueError(f"잘못된 recur 공휴일 형식입니다: {md} (MM-DD 필요)")

    @staticmethod
    def _compare_dates(start: datetime, end: datetime, label: str):
        """기간(start ≤ end) 검증"""
        if start > end:
            raise ValueError(f"{label} 시작일이 종료일보다 늦을 수 없습니다.")

    # ------------------------------------------------------------
    # ✅ 공휴일(recur/custom) 검사
    # ------------------------------------------------------------
    @staticmethod
    def validate_recur(list_md: list):
        for md in list_md:
            SettingsValidator._validate_recur(md)

    @staticmethod
    def validate_custom(list_md: list):
        for md in list_md:
            SettingsValidator._validate_recur(md)

    # ------------------------------------------------------------
    # ✅ 설/추석 기간 검사
    # ------------------------------------------------------------
    @staticmethod
    def validate_lunar(obj: dict, label: str):
        """
        {"start": "02.08", "days": 3}
        """
        if not obj:
            return

        start = obj.get("start")
        days = obj.get("days")

        if not start:
            return

        SettingsValidator._validate_md(start)

        if not isinstance(days, int) or days < 1 or days > 10:
            raise ValueError(f"{label}.days 값이 잘못되었습니다 (1~10 사이의 정수).")

    # ------------------------------------------------------------
    # ✅ 방학(BREAK_SUMMER, BREAK_WINTER, BREAK_SHORT) 검사
    # ------------------------------------------------------------
    @staticmethod
    def validate_range(obj: dict, label: str, allow_cross_year=False):
        """
        여름방학: {"start": "07.18", "end": "08.22"}  (MM.DD)
        겨울방학: {"start": "2026.12.28", "end": "2027.01.08"} (YYYY.MM.DD)
        """

        if not obj:
            return

        start = obj.get("start")
        end = obj.get("end")
        if not start or not end:
            return

        # 연도를 생략한 경우 → MM.DD
        if SettingsValidator.MD_PATTERN.match(start) and SettingsValidator.MD_PATTERN.match(end):
            # MM.DD → 현재 연도 기준에서 비교 불가 → 단순 MM,DD 비교
            SettingsValidator._validate_md(start)
            SettingsValidator._validate_md(end)

            # 비교를 위해 임의연도를 부여
            year = datetime.now().year
            s = datetime.strptime(f"{year}.{start}", "%Y.%m.%d")
            e = datetime.strptime(f"{year}.{end}", "%Y.%m.%d")

            SettingsValidator._compare_dates(s, e, label)
        else:
            # YYYY.MM.DD
            SettingsValidator._validate_ymd(start)
            SettingsValidator._validate_ymd(end)

            s = datetime.strptime(start, "%Y.%m.%d")
            e = datetime.strptime(end, "%Y.%m.%d")

            # 겨울방학은 연도跨越 허용
            if not allow_cross_year and s.year != e.year:
                raise ValueError(f"{label} 기간이 연도를 넘을 수 없습니다.")

            SettingsValidator._compare_dates(s, e, label)

    @staticmethod
    def validate_short_list(list_ranges: list):
        """단기방학 여러 개"""
        for r in list_ranges:
            SettingsValidator.validate_range(r, "단기방학(BREAK_SHORT)")

    # ------------------------------------------------------------
    # ✅ 운영시간(START_TIME, END_TIME)
    # ------------------------------------------------------------
    @staticmethod
    def validate_time_format(t: str, label: str):
        """
        HH:MM 형식 검사
        """
        try:
            datetime.strptime(t, "%H:%M")
        except Exception:
            raise ValueError(f"{label} 형식 오류: {t} (HH:MM 필요)")

    # ------------------------------------------------------------
    # ✅ 메인 Validator
    # ------------------------------------------------------------
    @staticmethod
    def validate(body: dict):
        """
        updateSchedule API에서 body 전체를 검사.
        실패 시 ValueError 발생.
        """

        # ✅ 운영시간
        if "START_TIME" in body:
            SettingsValidator.validate_time_format(body["START_TIME"], "START_TIME")
        if "END_TIME" in body:
            SettingsValidator.validate_time_format(body["END_TIME"], "END_TIME")

        # ✅ 국가공휴일 (recur + custom)
        SettingsValidator.validate_recur(body.get("HOLIDAY_RECUR", []))
        SettingsValidator.validate_custom(body.get("HOLIDAY_CUSTOM", []))

        # ✅ 설 / 추석
        SettingsValidator.validate_lunar(body.get("HOLIDAY_SEOL", {}), "HOLIDAY_SEOL")
        SettingsValidator.validate_lunar(body.get("HOLIDAY_CHUSEOK", {}), "HOLIDAY_CHUSEOK")

        # ✅ 여름방학
        SettingsValidator.validate_range(body.get("BREAK_SUMMER", {}), "여름방학(BREAK_SUMMER)")

        # ✅ 겨울방학 (연도跨越 허용)
        SettingsValidator.validate_range(
            body.get("BREAK_WINTER", {}),
            "겨울방학(BREAK_WINTER)",
            allow_cross_year=True
        )

        # ✅ 단기방학 여러개
        SettingsValidator.validate_short_list(body.get("BREAK_SHORT", []))

        return True
    
    