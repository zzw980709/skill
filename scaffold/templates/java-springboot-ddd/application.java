package {{basePackage}}.{{domainName}}.application;

import {{basePackage}}.{{domainName}}.domain.model.entity.{{EntityName}}Entity;
import {{basePackage}}.{{domainName}}.domain.repository.{{EntityName}}Repository;
import {{basePackage}}.{{domainName}}.interfaces.dto.{{EntityName}}Request;
import {{basePackage}}.common.exception.BaseException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;

/**
 * {{中文描述}}应用服务
 *
 * @author {{author}}
 * date {{date}}
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class {{EntityName}}Application {

    private final {{EntityName}}Repository {{entityName}}Repository;

    @Transactional(rollbackFor = Exception.class)
    public void create({{EntityName}}Request request) {
        // TODO(需求): 幂等/唯一性校验，命中时抛 BaseException(400, "{{i18nKey}}.exists")
        // if ({{entityName}}Repository.existsByName(request.getName())) {
        //     throw new BaseException(400, "{{i18nKey}}.exists");
        // }
        {{EntityName}}Entity entity = new {{EntityName}}Entity();
        // TODO(需求): 字段映射 entity.setXxx(request.getXxx());
        {{entityName}}Repository.save(entity);
    }

    public List<{{EntityName}}Entity> getAll() {
        return {{entityName}}Repository.findAll();
    }

    @Transactional(rollbackFor = Exception.class)
    public void update(String id, {{EntityName}}Request request) {
        Optional<{{EntityName}}Entity> opt = {{entityName}}Repository.findById(id);
        if (opt.isEmpty()) {
            // 数据不存在
            throw new BaseException(404, "{{i18nKey}}.not.exists");
        }
        {{EntityName}}Entity entity = opt.get();
        // entity.update(request.getXxx()); // 走实体 update()：空值保留 + touch()
        {{entityName}}Repository.save(entity);
    }

    @Transactional(rollbackFor = Exception.class)
    public void delete(String id) {
        {{entityName}}Repository.logicDeleteById(id);
    }
}
