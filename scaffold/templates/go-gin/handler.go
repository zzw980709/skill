// {{中文描述}}HTTP 处理
// ⚠️ 路由注册以活代码为准：gin RouterGroup / echo / chi…
package {{moduleName}}

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

type Handler struct {
	service *Service
}

// NewHandler: 依赖注入方式以活代码为准
func NewHandler(service *Service) *Handler {
	return &Handler{service: service}
}

// Register 挂载路由（路径/中间件以活代码为准）
func (h *Handler) Register(rg *gin.RouterGroup) {
	r := rg.Group("/{{mapping}}")
	r.GET("", h.List)
	r.POST("", h.Create)
	r.PUT("/:id", h.Update)
	r.DELETE("/:id", h.Delete)
}

func (h *Handler) List(c *gin.Context) {
	items, err := h.service.List(c.Request.Context())
	if err != nil {
		// ⚠️ 统一错误响应以活代码为准
		c.JSON(http.StatusInternalServerError, gin.H{"message": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": items})
}

func (h *Handler) Create(c *gin.Context) {
	var req CreateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		// ⚠️ 校验错误消息格式以活代码为准
		c.JSON(http.StatusBadRequest, gin.H{"message": err.Error()})
		return
	}
	// TODO(需求): 校验逻辑（binding 标签 / validator）
	if err := h.service.Create(c.Request.Context(), req); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"message": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "success"})
}

func (h *Handler) Update(c *gin.Context) {
	var req UpdateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"message": err.Error()})
		return
	}
	if err := h.service.Update(c.Request.Context(), c.Param("id"), req); err != nil {
		// ⚠️ NotFound 等状态码映射以活代码为准
		c.JSON(http.StatusInternalServerError, gin.H{"message": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "success"})
}

func (h *Handler) Delete(c *gin.Context) {
	if err := h.service.Delete(c.Request.Context(), c.Param("id")); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"message": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "success"})
}
