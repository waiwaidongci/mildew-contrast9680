"""对巡检记录分组，计算条件增长倍数并保留命中证据。"""

from collections import Counter, defaultdict
from datetime import date
from fractions import Fraction
from itertools import combinations

from .spec import SPEC


_CONDITION_LABELS = {
    "high_humidity": ("低于高湿切分点", "高湿"),
    "vent_blocked": ("风口未遮挡", "风口遮挡"),
    "maintenance_pending": ("无待结报修", "设施报修待结"),
}
_FIELDS = SPEC["fields"]
_PATTERN_COLUMNS = (
    ("pattern_id", "模式编号"), ("conditions", "伴随条件"), ("size", "条件数"),
    ("positive_count", "正组命中"), ("negative_count", "负组命中"),
    ("positive_support", "正组原始支持度"), ("negative_support", "负组原始支持度"),
    ("positive_smoothed", "正组平滑支持度"), ("negative_smoothed", "负组平滑支持度"),
    ("growth", "增长倍数"),
)
_EVIDENCE_COLUMNS = (("pattern_ids", "命中模式编号"),) + tuple(
    (field["key"], field["label"]) for field in _FIELDS
)


def _bounded(value, field):
    allowed = (int,) if field["type"] == "int" else (int, float)
    if type(value) not in allowed or not field["min"] <= value <= field["max"]:
        raise ValueError(f"{field['label']}须为 {field['min']} 至 {field['max']} 范围内的有效数值")
    return value


def validate_rows(rows):
    """校验导入与计算共用的巡检口径，返回独立记录。"""
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ValueError("请提供至少一条巡检记录")
    validated = []
    seen = set()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"第 {index} 条巡检记录格式有误")
        record = {}
        for field in _FIELDS:
            key, kind = field["key"], field["type"]
            value = row.get(key)
            try:
                if kind == "string":
                    if not isinstance(value, str) or not 1 <= len(value.strip()) <= field["max_length"]:
                        raise ValueError(f"{field['label']}为空或长度超限")
                    value = value.strip()
                elif kind == "date":
                    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                        raise ValueError
                elif kind == "bool":
                    if type(value) is not bool:
                        raise ValueError(f"{field['label']}须明确填写是或否")
                else:
                    value = _bounded(value, field)
            except ValueError as error:
                detail = "巡检日期须为有效的 YYYY-MM-DD 日期" if kind == "date" else str(error)
                raise ValueError(f"第 {index} 条巡检记录 · {detail}") from None
            record[key] = value
        inspection_id = record["inspection_id"]
        if inspection_id.casefold() in seen:
            raise ValueError(f"第 {index} 条巡检记录 · 巡检单号「{inspection_id}」重复")
        seen.add(inspection_id.casefold())
        validated.append(record)
    return validated


def _row_patterns(row, humidity_threshold):
    conditions = (
        ("high_humidity", row["humidity"] >= humidity_threshold),
        ("vent_blocked", row["vent_blocked"]),
        ("maintenance_pending", row["maintenance_pending"]),
    )
    return tuple((condition,) for condition in conditions) + tuple(combinations(conditions, 2))


def _score_patterns(hits, positives, negatives, params):
    alpha = Fraction(str(params["smoothing"]))
    minimum_growth = Fraction(str(params["min_growth"]))
    eligible = []
    for pattern, counts in hits.items():
        positive, negative = counts[True], counts[False]
        if positive < params["min_positive_count"] or positive + negative < params["min_total_count"]:
            continue
        positive_smoothed = (positive + alpha) / (positives + 2 * alpha)
        negative_smoothed = (negative + alpha) / (negatives + 2 * alpha)
        growth = positive_smoothed / negative_smoothed
        if growth >= minimum_growth:
            eligible.append((pattern, growth, positive, negative, positive_smoothed, negative_smoothed))
    eligible.sort(key=lambda item: (-item[1], -item[2], len(item[0]), item[0]))
    return eligible


def _table(title, columns, rows):
    return {"title": title, "columns": [{"key": key, "label": label} for key, label in columns], "rows": rows}


def analyze(rows, normalized_params):
    """对同一批有效巡检计算可重跑的单项及成对条件排名。"""
    records = validate_rows(rows)
    params = {
        field["key"]: _bounded(normalized_params.get(field["key"], field["default"]), field)
        for field in SPEC["params"]
    }
    total = len(records)
    positives = sum(row["mildew_observed"] for row in records)
    negatives = total - positives
    threshold = params["humidity_threshold"]
    patterns = []
    evidence = []
    if positives and negatives:
        hits = defaultdict(Counter)
        patterns_by_id = {}
        for row in records:
            matching = _row_patterns(row, threshold)
            patterns_by_id[row["inspection_id"]] = matching
            for pattern in matching:
                hits[pattern][row["mildew_observed"]] += 1

        pattern_ids = {}
        for rank, score in enumerate(_score_patterns(hits, positives, negatives, params), start=1):
            pattern, growth, positive, negative, positive_smoothed, negative_smoothed = score
            pattern_id = f"P{rank:02d}"
            pattern_ids[pattern] = pattern_id
            patterns.append({
                "pattern_id": pattern_id,
                "conditions": "且".join(_CONDITION_LABELS[field][value] for field, value in pattern),
                "size": len(pattern),
                "positive_count": positive,
                "negative_count": negative,
                "positive_support": positive / positives,
                "negative_support": negative / negatives,
                "positive_smoothed": float(positive_smoothed),
                "negative_smoothed": float(negative_smoothed),
                "growth": float(growth),
            })
        for row in sorted(records, key=lambda row: (row["inspection_date"], row["inspection_id"])):
            matching = sorted(pattern_ids[pattern] for pattern in patterns_by_id[row["inspection_id"]]
                              if pattern in pattern_ids)
            if matching:
                evidence.append({**row, "pattern_ids": "、".join(matching)})

    if not positives or not negatives:
        missing_group = "见霉斑" if not positives else "未见霉斑"
        headline = f"缺少{missing_group}的巡检记录，暂无法比较两组。"
    elif patterns:
        headline = f"筛出 {len(patterns)} 个伴随模式，{patterns[0]['conditions']}的增长倍数最高。"
    else:
        headline = "本批巡检中没有模式同时达到命中数与增长倍数门槛。"

    return {
        "state": "warning" if not positives or not negatives or patterns else "ok",
        "headline": headline,
        "note": (
            f"纳入 {total} 条巡检。湿度达到 {threshold:g}% 归入高湿，平滑量 {params['smoothing']:g}。"
            f"门槛为正组命中至少 {params['min_positive_count']} 条、两组合计至少 {params['min_total_count']} 条、"
            f"增长至少 {params['min_growth']:g} 倍。结果反映本批记录的关联，无法据此判定成因。"
        ),
        "metrics": [
            {"label": "见霉斑巡检", "value": positives, "detail": "正组支持度的分母"},
            {"label": "未见霉斑巡检", "value": negatives, "detail": "负组支持度的分母"},
            {"label": "入选模式", "value": len(patterns),
             "detail": f"单项 {sum(item['size'] == 1 for item in patterns)} 个，其余为成对条件"},
            {"label": "命中巡检", "value": len(evidence), "detail": "至少符合一个入选模式，按巡检单号计数"},
        ],
        "tables": [
            _table("伴随模式排名", _PATTERN_COLUMNS, patterns),
            _table("巡检证据明细", _EVIDENCE_COLUMNS, evidence),
        ],
        "charts": [{"title": "增长倍数最高的模式", "kind": "bar", "series": [
            {"label": item["pattern_id"], "value": item["growth"]} for item in patterns[:8]
        ]}] if patterns else [],
        "sections": [{"title": "按模式复核巡检", "text": (
            "用模式编号在巡检证据或下载的 CSV 中查找命中记录，再按巡检单号回查台账。"
            "同一条巡检可命中多个模式。按见霉斑列分组，可核对排名表的两组命中数。"
            "复核时查看同库房同期记录、连续湿度读数和设施报修单，再登记检查安排。"
        )}],
    }
