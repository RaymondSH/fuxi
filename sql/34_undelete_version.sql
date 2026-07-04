-- M3 后续修补：note_versions.change_type 增加 'undelete'。
-- 软删除恢复（POST /notes/{id}/restore）此前不留版本记录，恢复操作在版本历史里无痕；
-- 增加 undelete 值后，restore_note 会调 save_version(... "undelete" ...) 留痕。

ALTER TABLE note_versions DROP CONSTRAINT IF EXISTS note_versions_change_type_check;
ALTER TABLE note_versions ADD CONSTRAINT note_versions_change_type_check
    CHECK (change_type IN ('edit','refresh','restore','delete','undelete'));
