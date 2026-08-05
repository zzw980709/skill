// {{中文描述}}服务
package {{moduleName}}

import (
	"context"
	"errors"

	// ⚠️ 错误约定以活代码为准（哨兵错误 / 错误码 / 包装 error）
)

// ErrNotFound: 错误消息 key 以活代码为准
var ErrNotFound = errors.New("{{i18nKey}}.not_found")

type Service struct {
	repo *Repository
}

func NewService(repo *Repository) *Service {
	return &Service{repo: repo}
}

func (s *Service) List(ctx context.Context) ([]{{ModuleName}}, error) {
	return s.repo.List(ctx)
}

func (s *Service) Create(ctx context.Context, req CreateRequest) (*{{ModuleName}}, error) {
	// TODO(需求): 幂等/唯一性校验，命中时返回 ErrConflict 或业务错误
	// TODO(需求): 若跨表写，用事务（sqlx.Tx / gorm.Transaction）
	return s.repo.Create(ctx, req)
}

func (s *Service) Update(ctx context.Context, id string, req UpdateRequest) (*{{ModuleName}}, error) {
	obj, err := s.repo.GetByID(ctx, id)
	if err != nil {
		return nil, err
	}
	if obj == nil {
		return nil, ErrNotFound
	}
	// TODO(需求): 字段映射 / 空值保留约定
	return s.repo.Update(ctx, id, req)
}

func (s *Service) Delete(ctx context.Context, id string) error {
	// TODO(需求): 是否软删除以活代码为准
	return s.repo.SoftDelete(ctx, id)
}
