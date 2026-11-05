def mean_excluding_none(values: list[float | None]) -> float | None:
    """None은 평균에서 빼고, 남은 게 없으면 None. 0으로 바꾸지 않는다."""
    known = [v for v in values if v is not None]
    return sum(known) / len(known) if known else None
