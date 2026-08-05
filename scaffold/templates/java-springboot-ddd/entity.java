package {{basePackage}}.{{domainName}}.domain.model.entity;

import com.coloseo.altamira.customer.domain.model.entity.BaseEntity;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.Where;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.GenerationType;
import javax.persistence.Id;
import javax.persistence.Table;

/**
 * {{中文描述}}
 *
 * @author {{author}}
 * date {{date}}
 */
@Entity
@Table(name = "{{tableName}}")
// 含 jsonb 字段时才需要下面两行，否则删除：
// @TypeDef(name = "jsonb", typeClass = JsonBinaryType.class)
// import org.hibernate.annotations.TypeDef; import com.vladmihalcea.hibernate.type.json.JsonBinaryType;
@Where(clause = "deleted = false")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class {{EntityName}}Entity extends BaseEntity {

    @Id
    @Column(name = "id")
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private String id;

    // TODO(需求): 按业务字段补全。⚠️ 字段类型/注解以同域活代码为准
    @Column(name = "{{columnName}}")
    private {{fieldType}} {{fieldName}};

    // 更新方法：字段有空值保留约定时，setter 内判空 + 末尾 touch()
    // public void update(/* 入参 */) {
    //     this.{{fieldName}} = {{fieldName}};
    //     super.touch();
    // }
}
