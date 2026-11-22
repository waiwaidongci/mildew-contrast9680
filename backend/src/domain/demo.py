"""浦桥区档案馆五天的虚拟巡检台账。"""

from itertools import product


_ROOMS = ("东一库", "东二库", "北一库")
# 按高湿、风口遮挡、设施报修待结的布尔组合排列，每组五条巡检。
_POSITIVE_COUNTS = (0, 1, 1, 2, 1, 2, 4, 5)
_CONDITIONS = tuple(product((False, True), repeat=3))


def demo_rows() -> list[dict]:
    rows = []
    for day_index in range(5):
        date = f"2026-11-{16 + day_index}"
        for group, (high, blocked, pending) in enumerate(_CONDITIONS):
            room = _ROOMS[(day_index + group) % len(_ROOMS)]
            humidity = (65 if high else 55) + (day_index + group) % 5
            rows.append({
                "inspection_id": f"PQ-202611{16 + day_index}-{group + 1:02d}",
                "inspection_date": date,
                "room": room,
                "shelf": f"{chr(65 + group // 4)}-{group % 4 + 1:02d}",
                "humidity": humidity,
                "vent_blocked": blocked,
                "maintenance_pending": pending,
                "mildew_observed": (day_index + group) % 5 < _POSITIVE_COUNTS[group],
            })
    return rows
