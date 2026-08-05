// {{中文描述}}数据访问
// ⚠️ ORM 以活代码为准：sqlx / gorm / sqlc / database/sql…
package {{moduleName}}

import (
	"context"

	"github.com/jmoiron/sqlx"
)

type Repository struct {
	db *sqlx.DB
}

func NewRepository(db *sqlx.DB) *Repository {
	return &Repository{db: db}
}

func (r *Repository) List(ctx context.Context) ([]{{ModuleName}}, error) {
	rows := []{{ModuleName}}{}
	// ⚠️ 软删除 where 条件以活代码为准
	err := r.db.SelectContext(ctx, &rows, `SELECT * FROM {{tableName}} WHERE deleted = false`)
	return rows, err
}

func (r *Repository) GetByID(ctx context.Context, id string) (*{{ModuleName}}, error) {
	obj := &{{ModuleName}}{}
	err := r.db.GetContext(ctx, obj,
		`SELECT * FROM {{tableName}} WHERE id = $1 AND deleted = false`, id)
	if err != nil {
		return nil, err
	}
	return obj, nil
}

func (r *Repository) Create(ctx context.Context, req CreateRequest) (*{{ModuleName}}, error) {
	// TODO(需求): 字段映射；id 生成策略以活代码为准
	obj := &{{ModuleName}}{}
	// TODO(需求): INSERT 语句以活代码为准（占位符风格 $1/?）
	return obj, nil
}

func (r *Repository) Update(ctx context.Context, id string, req UpdateRequest) (*{{ModuleName}}, error) {
	// TODO(需求): 字段映射 / 空值保留约定
	return r.GetByID(ctx, id)
}

func (r *Repository) SoftDelete(ctx context.Context, id string) error {
	_, err := r.db.ExecContext(ctx, `UPDATE {{tableName}} SET deleted = true WHERE id = $1`, id)
	return err
}
