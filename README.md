# 🗄️ 星忆 StellarMemory

星缀套件的记忆数据层，兼容 Amo_data 表结构，可直接迁移旧数据。

## 功能

- 记忆读写（`recall` / `save`）
- 画像管理（`profile_get` / `profile_save`）
- 衣柜存储（`wardrobe_list` / `wardrobe_save`）
- 内置迁移工具（`migrate_from`）

## 迁移 Amo_data

**方式一：直接复制（推荐）**
```bash
cp ~/.astrbot/data/Astr_Amo_data/amo_data.db \
   ~/.astrbot/data/StellarMemory/stellar_memory.db
```

**方式二：指令迁移**
```
/stellar_migrate ~/.astrbot/data/Astr_Amo_data/amo_data.db
```

## 配置

| 项 | 默认 | 说明 |
|---|---|---|
| db_path | 自动 | 数据库路径，留空用默认 |
| recall_limit | 6 | 每次召回条数 |

---
v1.0.2 · 星缀套件 | https://github.com/zdx-ZDXA/StellarMemory
