package {{basePackage}}.{{domainName}}.interfaces.dto;

import {{basePackage}}.{{domainName}}.domain.model.entity.{{EntityName}}Entity;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * {{中文描述}}响应
 *
 * @author {{author}}
 * date {{date}}
 */
@Data
@NoArgsConstructor
public class {{EntityName}}Response {

    private String id;

    // TODO(需求): 按接口字段补全；与数据库列名不一致时用 @JsonProperty 标注下划线别名
    private String name;

    public {{EntityName}}Response({{EntityName}}Entity entity) {
        this.id = entity.getId();
        this.name = entity.getName();
    }
}
