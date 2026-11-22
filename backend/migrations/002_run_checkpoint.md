# 002 runs 增加核查断点列

`runs.checkpoint`（JSON，可空）保存架位去重稳健性核查的断点：`robustness` 为已核完模式的结论（模式键 → 结论），`total` 为待核模式总数。后台中断后重新领取运行时从断点续跑，全部核完才写入 `result` 并清空断点；运行失败同样清空。

启动时幂等执行：`ALTER TABLE runs ADD COLUMN IF NOT EXISTS checkpoint JSON`。新建数据库由 `create_all` 直接建出该列，迁移语句自动跳过。
