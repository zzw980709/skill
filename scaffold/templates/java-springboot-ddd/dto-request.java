package {{basePackage}}.{{domainName}}.interfaces.dto;

import com.coloseo.altamira.shop.interfaces.dto.OperatorRequest;
import lombok.Getter;
import lombok.Setter;

import javax.validation.constraints.NotBlank;

/**
 * {{中文描述}}请求
 *
 * @author {{author}}
 * date {{date}}
 */
@Getter
@Setter
// ⚠️ 仅当接口需要操作人身份（管理端/销售端）时继承 OperatorRequest，不需要就删
public class {{EntityName}}Request extends OperatorRequest {

    @NotBlank(message = "{{i18nKey}}.name.must.not.null")
    private String name;

    // TODO(需求): 按接口字段补全；校验注解的 message 一律用 i18n key，不用中文字面量
}
