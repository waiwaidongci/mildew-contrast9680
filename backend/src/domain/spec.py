"""档案库房巡检筛查的共享字段、参数和页面文案。"""


SPEC = {
    "title": "档案库房霉斑伴随条件筛查",
    "short_name": "mildew-contrast",
    "subtitle": "比较有霉斑与未见霉斑的巡检，查出值得复核的库房条件。",
    "organization": "浦桥区档案馆保管组，4 名保管员分班巡检三个库房，设施组负责风口和除湿设备。",
    "workflow": (
        "保管员按架位登记可见霉斑、现场相对湿度、风口遮挡和设施报修状态，每周汇总成 CSV。"
        "筛查按有霉斑和未见霉斑分组比较单项及成对条件。保管组按巡检单号复核，"
        "设施组根据复核记录安排现场检查。"
    ),
    "pains": [
        "只数有霉斑的记录，容易把两个组都常见的条件列入排查清单。",
        "在表格里逐项筛选时，很难同时看到两项条件共现的比例。",
        "组间比例差异很大时，现场人员还得回到原表核对样本量和架位。",
    ],
    "steps": [
        "11 月 20 日 15:00，合并 11 月 16–20 日的架位巡检单，保存为「浦桥档案库房巡检_20261116-20.csv」。",
        "在「巡检台账」导入 40 条巡检，核对每条记录的架位、现场湿度和报修状态。",
        "在「条件筛查」以 65% 为高湿切分点，设置平滑量 0.5、正组命中至少 3 条、两组合计至少 5 条。",
        "用默认的 1.5 倍增长门槛运行，确认有霉斑 16 条、未见霉斑 24 条。",
        "在「伴随模式与证据」找到「高湿且风口遮挡」，核对正组命中 9 条、负组命中 1 条。",
        "用模式编号查巡检证据，复核 PQ-20261116-07 的湿度、风口和架位。",
        "在「现场复核单」登记待检查的架位与设施，由设施组在「排查清单交接」下载结果。",
    ],
    "methodology": [
        "每个巡检单号计一条记录。见霉斑为正组，未见霉斑为负组。湿度达到切分点即计高湿，"
        "风口遮挡和报修待结均使用巡检时登记的状态。",
        "枚举各字段的两种取值，以及来自不同字段的两项条件。成对条件须同时成立。"
        "原始支持度为组内命中数 k 除以该组巡检总数 n。",
        "对命中和未命中各加同一平滑量 α，得平滑支持度 (k+α)/(n+2α)。"
        "增长倍数等于正组平滑支持度除以负组平滑支持度。任一组缺失时停止比较。",
        "模式须达到正组原始命中下限、两组合计原始命中下限和增长倍数下限。"
        "负组零命中允许入选。结果优先按增长倍数降序，同倍数时正组命中多的优先。",
        "结果用于确定复核顺序。库房差异、巡检日期和同一架位的重复巡检都可能影响关联，"
        "需结合湿度趋势和设施记录核查，无法据此判断霉斑成因。",
    ],
    "sample_name": "浦桥档案库房巡检_20261116-20.csv",
    "default_dataset": "浦桥区档案馆 11 月 16–20 日库房巡检",
    "entity": "巡检记录",
    "run": "条件筛查",
    "decision": "现场复核安排",
    "action": "登记复核安排",
    "modes": ["安排架位复查", "补录设施记录", "归档备查"],
    "pages": ["库房值班总览", "巡检台账", "条件筛查", "伴随模式与证据", "现场复核单", "排查清单交接"],
    "fields": [
        {"key": "inspection_id", "label": "巡检单号", "type": "string", "required": True, "max_length": 80},
        {"key": "inspection_date", "label": "巡检日期", "type": "date", "required": True},
        {"key": "room", "label": "库房", "type": "string", "required": True, "max_length": 80},
        {"key": "shelf", "label": "架位", "type": "string", "required": True, "max_length": 80},
        {"key": "humidity", "label": "相对湿度（%）", "type": "number", "required": True, "min": 0, "max": 100},
        {"key": "vent_blocked", "label": "风口遮挡", "type": "bool", "required": True},
        {"key": "maintenance_pending", "label": "设施报修待结", "type": "bool", "required": True},
        {"key": "mildew_observed", "label": "见霉斑", "type": "bool", "required": True},
    ],
    "params": [
        {"key": "humidity_threshold", "label": "高湿切分点（%）", "type": "number", "required": True,
         "min": 0, "max": 100, "default": 65, "help": "达到此值归入高湿，低于此值归入低于高湿切分点。"},
        {"key": "smoothing", "label": "平滑量 α", "type": "number", "required": True,
         "min": 0.01, "max": 10, "default": 0.5, "help": "每组对命中和未命中各加入 α，保留负组零命中的模式。"},
        {"key": "min_positive_count", "label": "正组最少命中", "type": "int", "required": True,
         "min": 1, "max": 5000, "default": 3, "help": "见霉斑的巡检中，至少有几条同时符合该模式的全部条件。"},
        {"key": "min_total_count", "label": "两组最少命中合计", "type": "int", "required": True,
         "min": 1, "max": 5000, "default": 5, "help": "两组原始命中数之和须达到此值。"},
        {"key": "min_growth", "label": "最低增长倍数", "type": "number", "required": True,
         "min": 1.01, "max": 5000, "default": 1.5, "help": "保留正组与负组平滑支持度之比达到此值的模式。"},
    ],
    "fixture": {"humidity_threshold": 68, "smoothing": 1, "min_total_count": 6},
    "axes": "横轴为增长倍数最高的模式编号，纵轴为正组与负组的平滑支持度之比。",
}
