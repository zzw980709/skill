"""Contract and change-rendering checks for the HTML generator."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

GENERATOR = Path(__file__).resolve().parents[1] / 'scripts/gen_api_doc.py'
spec = importlib.util.spec_from_file_location('api_doc', GENERATOR)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.doc = {
            'openapi': '3.0.3', 'info': {'title': 'test', 'version': '1'},
            'security': [{'Bearer': []}],
            'components': {
                'securitySchemes': {'Bearer': {'type': 'http', 'scheme': 'bearer'}},
                'parameters': {'ItemId': {'in': 'path', 'name': 'id', 'required': True,
                                          'schema': {'type': 'string', 'example': 'a/b'}}},
                'schemas': {'Item': {'type': 'object', 'required': ['id', 'URL', 'enabled'],
                    'properties': {'id': {'type': 'string', 'readOnly': True},
                                   'URL': {'type': 'string', 'description': '地址'},
                                   'password': {'type': 'string', 'writeOnly': True},
                                   'enabled': {'type': 'boolean', 'default': False},
                                   'children': {'type': 'array', 'items': {'$ref': '#/components/schemas/Item'}}}}}},
            'paths': {'/items/{id}': {'parameters': [{'$ref': '#/components/parameters/ItemId'}],
                'post': {'operationId': 'saveItem', 'summary': '保存条目',
                         'requestBody': {'required': True, 'content': {'application/json': {
                             'schema': {'$ref': '#/components/schemas/Item'}}}},
                         'responses': {'204': {'description': 'Saved'}, '409': {'description': 'Conflict'}}}}}}
        self.source = self.root / 'openapi.json'
        self.output = self.root / 'doc.html'

    def configure(self, modules=None, **extra):
        self.source.write_text(json.dumps(self.doc))
        gen.load_openapi.cache_clear()
        cfg = dict(title='测试', out=str(self.output),
                   modules=modules or [{'title': '管理端', 'openapi': str(self.source)}], **extra)
        gen.apply_config(cfg)
        return gen.collect_operations()

    def test_read_write_directions_in_field_tables(self):
        schema = {'$ref': '#/components/schemas/Item'}
        request = gen.field_table(schema, self.doc, 'request')
        response = gen.field_table(schema, self.doc, 'response')
        self.assertNotIn('>id<', request)
        self.assertIn('>id<', response)
        self.assertIn('password', request)
        self.assertNotIn('password', response)
        self.assertIn('URL', request)

    def test_inherited_ref_parameter(self):
        rec = self.configure()[0]
        self.assertEqual(rec['params'][0]['name'], 'id')

    def test_security_inheritance_override_and_unspecified(self):
        self.assertEqual(gen.auth_text({}, self.doc)[0], '需鉴权')
        self.assertEqual(gen.auth_text({'security': []}, self.doc)[0], '可匿名')
        self.assertEqual(gen.auth_text({'security': [{}]}, self.doc)[0], '可匿名')
        self.assertEqual(gen.auth_text({}, {})[0], '待确认')

    def test_nested_inline_array_paths_and_constraints(self):
        schema = {'type': 'object', 'properties': {'items': {'type': 'array', 'items': {
            'type': 'object', 'required': ['price'], 'properties': {
                'price': {'type': 'integer', 'minimum': 0, 'maximum': 999, 'description': '单位为分'},
                'status': {'type': 'string', 'enum': ['pending', 'paid'], 'nullable': True}}}}}}
        fields = gen.field_table(schema, self.doc, 'request')
        for value in ('items[].price', '单位为分', '最小值 0', '最大值 999', 'pending', '允许 null'):
            self.assertIn(value, fields)

    def test_search_includes_referenced_fields_but_not_unrelated_models(self):
        self.doc['components']['schemas']['Unrelated'] = {'properties': {'notThisField': {'type': 'string'}}}
        rec = self.configure()[0]
        text = gen.search_contract(rec['op'], self.doc)
        self.assertIn('enabled', text)
        self.assertIn('password', text)
        self.assertNotIn('notthisfield', text)

    def test_allof_merges_inherited_required_and_nested_composition(self):
        schema = {'allOf': [{'allOf': [{'type': 'object', 'required': ['a'], 'properties': {'a': {'type': 'string'}}}]},
                            {'type': 'object', 'properties': {'b': {'type': 'integer'}}}]}
        self.assertEqual(set(gen.shape(schema, self.doc)['properties']), {'a', 'b'})
        self.assertEqual(gen.shape(schema, self.doc)['required'], ['a'])

    def test_unresolved_refs_are_visible(self):
        self.assertEqual(gen.schema_type({'$ref': '#/components/schemas/Missing'}, self.doc), '未知引用')

    def test_json_property_with_extra_attributes(self):
        src = self.root / 'src'
        src.mkdir()
        (src / 'Order.java').write_text('''public class Order {
    /** 状态 */
    @JsonProperty(value = "order_status", required = true)
    private String orderStatus;
}
''', encoding='utf-8')
        docs = gen.extract_field_docs([str(src)])
        self.assertEqual(docs['Order'].get('order_status'), '状态')
        self.assertNotIn('orderStatus', docs['Order'])

    def test_nested_class_scope(self):
        src = self.root / 'src'
        src.mkdir()
        (src / 'Outer.java').write_text('''public class Outer {
    /** outer a */
    private String a;
    static class Inner {
        /** inner b */
        private String b;
    }
    /** outer c */
    private String c;
}
''', encoding='utf-8')
        docs = gen.extract_field_docs([str(src)])
        self.assertEqual(docs['Outer'].get('c'), 'outer c')
        self.assertNotIn('c', docs['Inner'])

    def test_boolean_schema_does_not_crash_handoff(self):
        self.doc['components']['schemas']['Flag'] = True
        records = self.configure()
        diffs = gen.compute_diffs(records)
        packet = gen.handoff_data(records, diffs)
        self.assertTrue(packet['operations'])

    def test_zero_operations_fails(self):
        self.doc['paths'] = {}
        self.configure()
        self.assertEqual(gen.build(), 1)
        self.assertFalse(self.output.exists())

    def test_diff_added_modified_removed(self):
        current = json.loads(json.dumps(self.doc))
        baseline = json.loads(json.dumps(self.doc))
        baseline['paths']['/old'] = {'get': {'operationId': 'old', 'responses': {'200': {'description': 'ok'}}}}
        current['paths']['/new'] = {'get': {'operationId': 'new', 'responses': {'200': {'description': 'ok'}}}}
        baseline['paths']['/items/{id}']['post']['requestBody']['content']['application/json']['schema'] = {
            '$ref': '#/components/schemas/Item'}
        current['paths']['/items/{id}']['post']['requestBody']['content']['application/json']['schema'] = {
            '$ref': '#/components/schemas/Item'}
        current['paths']['/items/{id}']['post']['parameters'] = [{'name': 'status', 'in': 'query', 'schema': {'type': 'string'}}]
        current['paths']['/items/{id}']['post']['responses']['201'] = {'description': 'Created'}
        baseline['components']['schemas']['Item']['properties']['legacy'] = {'type': 'string'}
        current['components']['schemas']['Item']['properties']['note'] = {'type': 'string'}
        for name in ('current.json', 'baseline.json'):
            (self.root / name).write_text(json.dumps(current if name.startswith('current') else baseline), encoding='utf-8')
        gen.load_openapi.cache_clear()
        cfg = dict(title='变更', out=str(self.output), baselineLabel='生产环境 pro', baselineDate='2026-11-18',
                   modules=[{'title': '管理端', 'openapi': str(self.root / 'current.json'),
                             'baseline': str(self.root / 'baseline.json')}])
        gen.apply_config(cfg)
        records = gen.collect_operations()
        diffs = gen.compute_diffs(records)
        self.assertEqual((diffs['added'], diffs['modified'], diffs['removed']), (1, 1, 1))
        modified = next(r for r in records if r.get('change_status') == 'modified')
        fields = {c['field'] for c in modified['changes']}
        self.assertIn('query.status', fields)
        self.assertIn('note', fields)
        self.assertIn('201', fields)
        self.assertIn('legacy', fields)
        self.assertTrue(modified['breaking'])
        self.assertEqual(gen.build(), 0)
        html = self.output.read_text()
        self.assertIn('id="changes"', html)
        self.assertIn('change-rail', html)
        self.assertIn('生产环境 pro', html)
        self.assertNotIn('code-rail', html)
        self.assertNotIn('TypeScript', html)

    def test_multiple_modules_same_routes_have_unique_anchors(self):
        records = self.configure(modules=[{'title': '管理端', 'openapi': str(self.source)},
                                          {'title': '客户端', 'openapi': str(self.source)}])
        self.assertNotEqual(records[0]['id'], records[1]['id'])
        self.assertEqual(gen.build(), 0)
        self.assertFalse(any(gen.verify(self.output.read_text()).values()))

    def test_ambiguous_workflow_fails_before_writing(self):
        self.configure(modules=[{'title': '管理端', 'openapi': str(self.source)},
                                {'title': '客户端', 'openapi': str(self.source)}],
                       workflows=[{'title': '流程', 'steps': [{'operationId': 'saveItem'}]}])
        with self.assertRaisesRegex(ValueError, '唯一匹配'):
            gen.build()
        self.assertFalse(self.output.exists())

    def test_workflow_links_notes_and_untrusted_text_are_safe(self):
        self.doc['paths']['/items/{id}']['post']['summary'] = '</script><img src=x onerror=alert(1)>'
        records = self.configure(workflows=[{'title': '保存流程', 'steps': [{'operationId': 'saveItem'}]}],
                                 operationDocs={'saveItem': {'usage': '<b>调用时机</b>', 'notes': ['刷新列表']}})
        self.assertEqual(gen.build(), 0)
        output = self.output.read_text()
        self.assertIn('href="#' + records[0]['id'] + '"', output)
        self.assertIn('&lt;b&gt;调用时机&lt;/b&gt;', output)
        self.assertNotIn('<img src=x', output)
        self.assertNotIn('<script src=', output)
        self.assertIn('刷新列表', output)

    def test_checker_rejects_duplicate_ids_and_broken_links(self):
        result = gen.verify('<div id="x"></div><div id="x"><a href="#missing">go</a></div>')
        self.assertEqual(result['duplicate_ids'], ['x'])
        self.assertEqual(result['broken_anchors'], ['missing'])


if __name__ == '__main__':
    unittest.main()
