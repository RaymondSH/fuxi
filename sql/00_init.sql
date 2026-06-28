-- 按顺序执行所有初始化脚本
-- psql -U postgres -d fuxi -f sql/00_init.sql

\i sql/01_extensions.sql
\i sql/02_notes.sql
\i sql/03_graph.sql
\i sql/04_wiki.sql
\i sql/05_history.sql
\i sql/06_jobs.sql
