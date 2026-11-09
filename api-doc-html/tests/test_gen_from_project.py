"""Offline regression checks for export scope and file-only generation.

Run: python3 -m unittest discover -s api-doc-html/tests -v
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'gen_from_project.sh'


class ProjectExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='api docs test ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / 'project with spaces'
        (self.project / 'src/main/java').mkdir(parents=True)
        self.log = self.root / 'args.json'
        self.exporter = self.root / 'fake exporter'
        self.exporter.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
pathlib.Path(os.environ['TEST_EXPORT_ARGS']).write_text(json.dumps(args))
if '--dry-run' not in args:
    sys.exit('file-only export must pass --dry-run')
doc = {'openapi': '3.0.0', 'info': {'title': 'Test', 'version': '1'},
       'servers': [{'url': 'http://localhost:8080'}],
       'paths': {'/orders': {'get': {'operationId': 'listOrders',
                 'responses': {'200': {'description': 'OK'}}}}}}
pathlib.Path(args[args.index('--out') + 1]).write_text(json.dumps(doc))
''', encoding='utf-8')
        self.exporter.chmod(0o755)
        self.env = dict(os.environ, TEST_EXPORT_ARGS=str(self.log),
                        API_EXPORTER_BIN=str(self.exporter),
                        APIFOX_TOKEN='fake-test-token', APIFOX_PROJECT_ID='123')

    def run_script(self, *args):
        return subprocess.run(['bash', str(SCRIPT), *args], cwd=self.root,
                              env=self.env, text=True, capture_output=True)

    def base_args(self):
        return ['--project', str(self.project), '--out', 'output/docs.html']

    def test_filtered_export_is_local_and_preserves_paths(self):
        result = self.run_script(*self.base_args(), '--include', 'GET /orders',
                                 '--exclude', 'http:DELETE',
                                 '--keep-openapi', 'output/openapi.json')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        args = json.loads(self.log.read_text())
        self.assertIn('--dry-run', args)
        self.assertEqual(args[args.index('--include') + 1], 'GET /orders')
        self.assertEqual(args[args.index('--exclude') + 1], 'http:DELETE')
        self.assertTrue((self.root / 'output/docs.html').is_file())
        self.assertIn('/orders', json.loads((self.root / 'output/openapi.json').read_text())['paths'])

    def test_explicit_all(self):
        result = self.run_script(*self.base_args(), '--all')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('--include', json.loads(self.log.read_text()))

    def test_scope_is_required(self):
        result = self.run_script(*self.base_args())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--include', result.stderr)
        self.assertFalse(self.log.exists())

    def test_all_and_include_conflict_in_both_orders(self):
        for scope in (['--all', '--include', 'GET /orders'],
                      ['--include', 'GET /orders', '--all']):
            with self.subTest(scope=scope):
                result = self.run_script(*self.base_args(), *scope)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.log.exists())

    def test_missing_option_value(self):
        for suffix in (['--include'], ['--include', '--all']):
            with self.subTest(suffix=suffix):
                result = self.run_script(*self.base_args(), *suffix)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('缺少参数值', result.stderr)
                self.assertFalse(self.log.exists())


if __name__ == '__main__':
    unittest.main()
