package {{basePackage}}.{{domainName}}.interfaces.controller;

import {{basePackage}}.{{domainName}}.application.{{EntityName}}Application;
import {{basePackage}}.{{domainName}}.domain.model.entity.{{EntityName}}Entity;
import {{basePackage}}.{{domainName}}.interfaces.dto.{{EntityName}}Request;
import {{basePackage}}.{{domainName}}.interfaces.dto.{{EntityName}}Response;
import {{basePackage}}.common.dto.DataResponse;
import {{basePackage}}.common.dto.Message;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import javax.validation.Valid;
import java.util.List;
import java.util.stream.Collectors;

/**
 * {{中文描述}}
 *
 * @author {{author}}
 * date {{date}}
 */
@RestController
@RequestMapping("/{{mapping}}")
@RequiredArgsConstructor
public class {{EntityName}}Controller {

    private final {{EntityName}}Application {{entityName}}Application;

    @GetMapping
    public ResponseEntity<DataResponse<List<{{EntityName}}Response>>> list() {
        List<{{EntityName}}Entity> entities = {{entityName}}Application.getAll();
        List<{{EntityName}}Response> responses = entities.stream()
                .map({{EntityName}}Response::new)
                .collect(Collectors.toList());
        return ResponseEntity.ok(new DataResponse<>(responses));
    }

    @PostMapping
    public ResponseEntity<Message> create(@RequestBody @Valid {{EntityName}}Request request) {
        {{entityName}}Application.create(request);
        return ResponseEntity.ok(new Message("success"));
    }

    @PutMapping("/{id}")
    public ResponseEntity<Message> update(@PathVariable String id,
                                          @RequestBody @Valid {{EntityName}}Request request) {
        {{entityName}}Application.update(id, request);
        return ResponseEntity.ok(new Message("success"));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Message> delete(@PathVariable String id) {
        {{entityName}}Application.delete(id);
        return ResponseEntity.ok(new Message("success"));
    }
}
