-- {{中文描述}}（示例 DDL；⚠️ 若用 Prisma / Flyway 等，迁移写法以活代码为准）
create table if not exists {{tableName}}
(
    id         text         default gen_random_uuid() not null primary key,
    -- TODO(需求): 业务字段
    name       text         null,
    created_at timestamptz  not null default now(),
    updated_at timestamptz  not null default now(),
    deleted    boolean      not null default false
);
-- 关键字段加索引：按实际查询条件选择
-- create unique index uk_{{tableName}}_name on {{tableName}} (name) where deleted = false;
