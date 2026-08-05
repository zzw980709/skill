package {{basePackage}}.{{domainName}}.domain.repository;

import {{basePackage}}.{{domainName}}.domain.model.entity.{{EntityName}}Entity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import java.util.Optional;

/**
 * {{中文描述}}仓储
 *
 * @author {{author}}
 * date {{date}}
 */
public interface {{EntityName}}Repository extends JpaRepository<{{EntityName}}Entity, String> {

    // 简单查询优先用 derived method：
    // Optional<{{EntityName}}Entity> findByName(String name);
    // boolean existsByName(String name);

    // 逻辑删除：实体有 @Where(deleted=false)，删除必须走此方法，不能直接 delete
    // ⚠️ 是否带 updated_at = now() 以同域写法为准
    @Modifying
    @Query(nativeQuery = true,
            value = "update {{tableName}} set deleted = true where id = ?1")
    void logicDeleteById(String id);

    // 分页/联表/复杂查询：优先 Querydsl；写原生 SQL 时 select 字段别名必须与实体属性一致
}
