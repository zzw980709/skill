-- {{中文描述}}
create table if not exists {{tableName}}
(
    id         text                 default gen_random_uuid() not null primary key,
    -- TODO(需求): 业务字段，字符串统一 text 类型
    name       text        null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    deleted    boolean     not null default false
);
-- 备注
comment on table {{tableName}} is '{{中文描述}}';
comment on column {{tableName}}.name is '名称';
-- 关键字段加索引：按实际查询条件选择（唯一键/频繁 where 的列）
-- create unique index uk_{{tableName}}_name on {{tableName}} (name) where deleted = false;
