// {{中文描述}}请求/响应
// ⚠️ 校验方式以活代码为准（binding 标签 / validator / 手写校验）
package {{moduleName}}

type CreateRequest struct {
	// TODO(需求): 按接口字段补全
	Name string `json:"name" binding:"required"`
}

type UpdateRequest struct {
	// TODO(需求): 按接口字段补全
	Name *string `json:"name"`
}

type Response struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}
