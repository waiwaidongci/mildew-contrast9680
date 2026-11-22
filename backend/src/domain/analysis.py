"""对巡检记录分组，计算条件增长倍数并保留命中证据。"""

from collections import Counter, defaultdict
from datetime import date
from fractions import Fraction
from itertools import combinations

from .spec import SPEC

_FIELD_INDEX = {"high_humidity": 0, "vent_blocked": 1, "maintenance_pending": 2}
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


# ---------- 架位去重稳健性核查 ----------
#
# 同一库房的同一架位可能有多条巡检，重复记录会把条件推上榜。核查时每个库房的
# 每个架位只留一条：留法随架位数组合爆炸，但组内记录按（是否见霉斑 × 是否命中）
# 归并后只有四种类型，可以对各门槛直接求任意留法下的精确最坏情形，不抽样。

_ROBUSTNESS_COLUMNS = (
    ("pattern_id", "模式编号"), ("conditions", "伴随条件"), ("verdict", "核查结论"),
    ("reason", "复算依据"), ("selection", "反例巡检单号（每库每架位各留一条）"),
)


def _pattern_key(pattern):
    return "|".join(f"{field}={int(value)}" for field, value in pattern)


def _shelf_groups(records, threshold):
    """按（库房，架位）分组，组内与组间顺序保持确定，保证反例可复算。"""
    groups = defaultdict(list)
    for row in records:
        groups[(row["room"], row["shelf"])].append({
            "inspection_id": row["inspection_id"],
            "inspection_date": row["inspection_date"],
            "mold": row["mildew_observed"],
            "conditions": (row["humidity"] >= threshold, row["vent_blocked"], row["maintenance_pending"]),
        })
    return [(key, sorted(members, key=lambda item: (item["inspection_date"], item["inspection_id"])))
            for key, members in sorted(groups.items())]


def _group_reps(members, pattern):
    """组内记录按（见霉斑, 命中）归并，每类留一条代表记录。"""
    reps = {}
    for item in members:
        hit = all(item["conditions"][_FIELD_INDEX[field]] == value for field, value in pattern)
        reps.setdefault((item["mold"], hit),
                        {"inspection_id": item["inspection_id"], "mold": item["mold"], "hit": hit})
    return reps


def _pick(reps, order):
    for kind in order:
        if kind in reps:
            return reps[kind]
    raise ValueError("架位组内没有可保留的巡检记录")


def _recount(selection):
    positives = sum(item["mold"] for item in selection)
    negatives = len(selection) - positives
    hit_positive = sum(item["mold"] and item["hit"] for item in selection)
    hit_negative = sum(not item["mold"] and item["hit"] for item in selection)
    return positives, negatives, hit_positive, hit_negative


def _counterexample(selection, reason, params, alpha, minimum_growth):
    """汇总一套使模式掉出榜单的留法，并回算校验它确实未上榜。"""
    positives, negatives, hit_positive, hit_negative = _recount(selection)
    failures = []
    if not positives or not negatives:
        failures.append("一组为空")
    if hit_positive < params["min_positive_count"]:
        failures.append("正组命中不足")
    if hit_positive + hit_negative < params["min_total_count"]:
        failures.append("两组合计命中不足")
    if positives and negatives:
        growth = ((hit_positive + alpha) / (positives + 2 * alpha)) / ((hit_negative + alpha) / (negatives + 2 * alpha))
        if growth < minimum_growth:
            failures.append("增长倍数不足")
    if not failures:
        raise ValueError("架位去重核查内部校验失败，请重新运行")
    recount = (f"按所附 {len(selection)} 条单号（每个库房的每个架位各一条）复算：见霉斑 {positives} 条、"
               f"未见霉斑 {negatives} 条、正组命中 {hit_positive} 条、负组命中 {hit_negative} 条")
    return {
        "stable": False,
        "reason": f"{reason}。{recount}。",
        "selection": [item["inspection_id"] for item in selection],
        "recount": {"positives": positives, "negatives": negatives,
                    "positive_hits": hit_positive, "negative_hits": hit_negative},
    }


def verify_pattern(groups, pattern, params):
    """精确判断模式在任意「每库每架位留一条」的留法下是否仍按原门槛上榜。

    groups 为 _shelf_groups 的结果；返回稳定结论或一套反例留法。
    """
    alpha = Fraction(str(params["smoothing"]))
    minimum_growth = Fraction(str(params["min_growth"]))
    min_positive = params["min_positive_count"]
    min_total = params["min_total_count"]
    typed = [(key, _group_reps(members, pattern)) for key, members in groups]
    total = len(typed)

    # 正组命中压到最低：组内全是「见霉斑且命中」的记录时躲不掉，其余组都能避开。
    forced_positive = sum(set(reps) == {(True, True)} for _, reps in typed)
    if forced_positive < min_positive:
        selection = [reps[(True, True)] if set(reps) == {(True, True)}
                     else _pick(reps, ((False, True), (False, False), (True, False)))
                     for _, reps in typed]
        return _counterexample(selection, f"存在留法使正组命中降至 {forced_positive} 条，"
                                          f"低于正组最少命中 {min_positive} 条",
                               params, alpha, minimum_growth)

    # 两组命中合计压到最低：组内全部命中时躲不掉，其余组都能留未命中记录。
    forced_hit = sum(all(hit for _, hit in reps) for _, reps in typed)
    if forced_hit < min_total:
        selection = [_pick(reps, ((False, False), (True, False))) if not all(hit for _, hit in reps)
                     else _pick(reps, ((False, True), (True, True)))
                     for _, reps in typed]
        return _counterexample(selection, f"存在留法使两组命中合计降至 {forced_hit} 条，"
                                          f"低于两组最少命中合计 {min_total} 条",
                               params, alpha, minimum_growth)

    # 组分类：只能留见霉斑、只能留未见霉斑、两者皆可。
    entries = []
    for key, reps in typed:
        has_mold = (True, False) in reps or (True, True) in reps
        has_plain = (False, False) in reps or (False, True) in reps
        kind = "free" if has_mold and has_plain else ("mold" if has_mold else "plain")
        entries.append((key, reps, kind))
    forced_mold = sum(kind == "mold" for _, _, kind in entries)
    forced_plain = sum(kind == "plain" for _, _, kind in entries)

    # 增长倍数压到最低。固定留见霉斑记录的组数 p 后，每组代价只与命中类型有关：
    # 留「见霉斑且命中」代价 a，留「未见霉斑且命中」代价 -b，其余为 0，
    # 其中 a = 负组组数 + 2α，b = 增长门槛 ×（正组组数 + 2α）。各 p 的最坏留法由
    # 自由组代价差（0、b、a、a+b 四档）升序凑出，逐 p 精确求最小值，不枚举组合。
    costly_mold = sum(kind == "mold" and (True, False) not in reps for _, reps, kind in entries)
    negative_hit = sum(kind != "mold" and (False, True) in reps for _, reps, kind in entries)
    c0 = ca = cb = cab = 0
    for _, reps, kind in entries:
        if kind != "free":
            continue
        avoidable = (True, False) in reps
        negative = (False, True) in reps
        if avoidable and negative:
            cb += 1
        elif avoidable:
            c0 += 1
        elif negative:
            cab += 1
        else:
            ca += 1
    best = None
    low = max(forced_mold, 1)
    high = min(total - forced_plain, total - 1)
    for p in range(low, high + 1):
        a = Fraction(total - p) + 2 * alpha
        b = minimum_growth * (Fraction(p) + 2 * alpha)
        rest = p - forced_mold - min(p - forced_mold, c0)
        first, second = ((ca, a), (cb, b)) if a <= b else ((cb, b), (ca, a))
        take_first = min(rest, first[0])
        rest -= take_first
        take_second = min(rest, second[0])
        rest -= take_second
        objective = (costly_mold * a - negative_hit * b
                     + take_first * first[1] + take_second * second[1] + rest * (a + b)
                     + alpha * (a - b))
        if best is None or objective < best[0]:
            best = (objective, p)
    if best is not None and best[0] < 0:
        p = best[1]
        a = Fraction(total - p) + 2 * alpha
        b = minimum_growth * (Fraction(p) + 2 * alpha)
        deltas = []
        for key, reps, kind in entries:
            if kind != "free":
                continue
            mold_cost = Fraction(0) if (True, False) in reps else a
            plain_cost = -b if (False, True) in reps else Fraction(0)
            deltas.append((mold_cost - plain_cost, key, reps))
        deltas.sort(key=lambda item: (item[0], item[1]))
        leave_mold = {key for _, key, _ in deltas[:p - forced_mold]}
        selection = []
        for key, reps, kind in entries:
            if kind == "mold" or key in leave_mold:
                selection.append(_pick(reps, ((True, False), (True, True))))
            else:
                selection.append(_pick(reps, ((False, True), (False, False))))
        positives, negatives, hit_positive, hit_negative = _recount(selection)
        growth = float(((hit_positive + alpha) / (positives + 2 * alpha))
                       / ((hit_negative + alpha) / (negatives + 2 * alpha)))
        return _counterexample(selection, f"存在留法使增长倍数降至 {growth:.4g}，"
                                          f"低于最低增长倍数 {float(minimum_growth):g}",
                               params, alpha, minimum_growth)

    # 某一组被留空：无法比较两组，同样算反例。
    if forced_mold == 0:
        selection = [_pick(reps, ((False, False), (False, True))) for _, reps, _ in entries]
        return _counterexample(selection, "存在留法使见霉斑一组为空，无法比较两组",
                               params, alpha, minimum_growth)
    if forced_plain == 0:
        selection = [_pick(reps, ((True, False), (True, True))) for _, reps, _ in entries]
        return _counterexample(selection, "存在留法使未见霉斑一组为空，无法比较两组",
                               params, alpha, minimum_growth)

    return {
        "stable": True,
        "reason": (f"任意留法下正组命中至少 {forced_positive} 条、两组命中合计至少 {forced_hit} 条、"
                   f"增长倍数均达到 {float(minimum_growth):g} 倍，且两组均不为空"),
        "selection": None,
        "recount": None,
    }


def robustness_report(rows, normalized_params, done=None, on_verified=None):
    """对上榜模式逐一做架位去重核查，返回可并入分析结果的报告。

    done 为断点中已核完的模式结论（模式键 → 结论），on_verified 在每核完一个
    模式后回调（模式键、结论、模式总数），供后台落盘断点；全部核完才返回报告。
    两组缺失或没有上榜模式时返回 None。
    """
    records = validate_rows(rows)
    params = {
        field["key"]: _bounded(normalized_params.get(field["key"], field["default"]), field)
        for field in SPEC["params"]
    }
    positives = sum(row["mildew_observed"] for row in records)
    negatives = len(records) - positives
    if not positives or not negatives:
        return None
    hits = defaultdict(Counter)
    for row in records:
        for pattern in _row_patterns(row, params["humidity_threshold"]):
            hits[pattern][row["mildew_observed"]] += 1
    eligible = _score_patterns(hits, positives, negatives, params)
    if not eligible:
        return None
    groups = _shelf_groups(records, params["humidity_threshold"])
    done = done or {}
    verdicts = {}
    for rank, score in enumerate(eligible, start=1):
        pattern = score[0]
        key = _pattern_key(pattern)
        verdict = done.get(key)
        if verdict is None:
            verdict = verify_pattern(groups, pattern, params)
            verdict["pattern_id"] = f"P{rank:02d}"
            verdict["conditions"] = "且".join(_CONDITION_LABELS[field][value] for field, value in pattern)
            if on_verified:
                on_verified(key, verdict, len(eligible))
        verdicts[key] = verdict
    ordered = [verdicts[_pattern_key(score[0])] for score in eligible]
    stable = sum(item["stable"] for item in ordered)
    table_rows = [{
        "pattern_id": item["pattern_id"],
        "conditions": item["conditions"],
        "verdict": "稳健上榜" if item["stable"] else "存在反例",
        "reason": item["reason"],
        "selection": "、".join(item["selection"]) if item["selection"] else "",
    } for item in ordered]
    return {
        "metric": {"label": "架位去重后稳健上榜", "value": f"{stable}/{len(ordered)}",
                   "detail": "每个库房的每个架位各留一条巡检，任意留法下仍按原门槛上榜的模式数"},
        "table": _table("架位去重稳健性核查", _ROBUSTNESS_COLUMNS, table_rows),
        "section": {"title": "架位去重核查口径", "text": (
            "同一库房的同一架位只留一条巡检。留法随架位数组合爆炸，核查不抽样：组内记录按"
            "（是否见霉斑 × 是否命中）归并后，对正组命中、两组合计命中和增长倍数分别求任意"
            "留法下的精确最坏情形，上千个架位也能给出确定结论。任何留法都上榜的模式记为"
            "「稳健上榜」；否则记为「存在反例」，并附一套使其掉出榜单的巡检单号，按单号筛出"
            "台账、以原参数复算即可验证。某种留法使见霉斑或未见霉斑一组为空的，同样记为反例。"
            "核查在后台逐模式断点续跑，中断后从已核完的模式继续，全部核完才写入本页结果。"
        )},
        "note": f"架位去重核查：{stable} 个模式任意留法均上榜，{len(ordered) - stable} 个存在反例，反例单号见核查表。",
    }


def merge_robustness(result, report):
    """把核查报告并入分析结果：指标、排名表之后的核查表、说明与口径。"""
    result["metrics"].append(report["metric"])
    result["tables"].insert(1, report["table"])
    result["sections"].insert(0, report["section"])
    result["note"] += report["note"]
    return result
