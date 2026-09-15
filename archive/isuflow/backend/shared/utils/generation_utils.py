from datetime import datetime


# ✅ 1) 현재 연도 기준 → 현재 기수 계산
# 문서 4.4.1 기반:
# generation = floor((year - 2024) / 3) + 1
def get_current_generation() -> int:
    year = datetime.now().year
    gen = ((year - 2024) // 3) + 1
    return gen


# ✅ 2) 특정 year → 해당 기수 계산
def get_generation_by_year(year: int) -> int:
    gen = ((year - 2024) // 3) + 1
    return gen


# ✅ 3) 기수 → 연도 블록 문자열 ("2024-2026")
def get_generation_years(gen: int) -> str:
    """
    gen=1 → 2024~2026
    gen=2 → 2027~2029
    ...
    """
    start = 2024 + (gen - 1) * 3
    end = start + 2
    return f"{start}-{end}"


# ✅ 4) 현재 기수가 마지막 연도인지 체크 (아카이브 조건과 사용 가능)
def is_last_year_of_generation() -> bool:
    """
    예: 1기 = 2024~2026
      → 2026년이 마지막 해
    """
    gen = get_current_generation()
    block = get_generation_years(gen)
    start, end = block.split("-")
    last_year = int(end)

    return datetime.now().year == last_year


# ✅ 5) 연도 범위 리턴 (튜플)
def get_generation_range(gen: int):
    block = get_generation_years(gen)
    s, e = block.split("-")
    return int(s), int(e)


# ✅ 6) 기수 전환 여부 판단 (ex: 2026→2027 전환)
def is_generation_change() -> bool:
    """
    현재 연도가 속한 기수와,
    내년이 속한 기수가 다르면 기수 전환.
    """
    this_year = datetime.now().year
    next_year = this_year + 1

    gen_now = get_generation_by_year(this_year)
    gen_next = get_generation_by_year(next_year)

    return gen_now != gen_next


