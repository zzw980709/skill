// {{中文描述}}模型
// ⚠️ 是否继承基类 / id 策略 / 审计字段以活代码为准（gorm 用 gorm.Model 或有自己的 BaseModel）
package {{moduleName}}

import "time"

type {{ModuleName}} struct {
	ID        string    `db:"id" json:"id"`
	Name      string    `db:"name" json:"name"`
	CreatedAt time.Time `db:"created_at" json:"created_at"`
	UpdatedAt time.Time `db:"updated_at" json:"updated_at"`
	Deleted   bool      `db:"deleted" json:"-"`
}
