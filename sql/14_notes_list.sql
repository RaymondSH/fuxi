-- M1 步骤1：笔记列表/浏览页所需列。
--   authority REAL    权威度占位列，本轮不进排序（权重进排序留 M3 巡检），先建避免再迁移。
--   views_count INT   笔记详情被查看次数（GET /notes/{id} 时 +1），列表页可选展示热度。
-- 幂等：重复执行不报错。

ALTER TABLE notes ADD COLUMN IF NOT EXISTS authority REAL NOT NULL DEFAULT 0.5;
ALTER TABLE notes ADD COLUMN IF NOT EXISTS views_count INT NOT NULL DEFAULT 0;
