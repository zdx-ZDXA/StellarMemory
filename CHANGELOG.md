# 更新日志

## 1.0.3

- 补齐 `CHANGELOG.md`（AstrBot 启动告警消除）。

## 1.0.2

- `_conf_schema.json` 改为 AstrBot 扁平字典格式，修复加载时
  `TypeError: string indices must be integers, not 'str'`。

## 1.0.1

- 去掉 `@register` 装饰器，改为 `class StellarMemory(Star)` 直接继承。
- 修复 AstrBot 4.x 导入路径。

## 1.0.0

- 记忆层：`recall` / `save`（幂等去重）/ `profile_get` / `profile_save`。
- 衣柜：`wardrobe_list` / `wardrobe_save` / `wardrobe_delete`。
- 迁移工具 `migrate_from(源库路径)`，统计并复制 memories / profiles / wardrobe。
- 表结构与 Astrbot_Amo_data 完全一致：
  - `memories` 14 字段（含 scope / group_id / importance / idem_key / superseded_by）
  - `profiles` 7 字段
  - `wardrobe` 10 字段（复合主键 bot_id + id）
