import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parent
if not (ROOT / 'server.py').exists():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
import codex_runner
spec = importlib.util.spec_from_file_location('devflow_server_test', ROOT / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class CodexTests(unittest.TestCase):
    def fake(self, tmp, behavior):
        script = Path(tmp) / 'fake-codex'
        script.write_text('#!/usr/bin/env python3\nimport json,sys,time,pathlib\n' + behavior)
        script.chmod(0o700)
        return str(script)

    def test_stream_and_final_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = self.fake(tmp, '''
assert '--sandbox' in sys.argv and 'read-only' in sys.argv
assert 'approval_policy="never"' in sys.argv
assert sys.stdin.read() == 'prompt'
print(json.dumps({'type':'thread.started','thread_id':'t1'}))
print(json.dumps({'type':'item.started','item':{'type':'command_execution','command':'rg foo'}}))
print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'intermediate'}}))
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':12}}))
pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('final')
''')
            steps = []
            with patch.object(codex_runner, 'executable', return_value=binary):
                out = codex_runner.run('prompt', tmp, tmp + '/run.jsonl', 5,
                                       on_step=lambda *a: steps.append(a))
            self.assertEqual(out['message'], 'final')
            self.assertEqual(out['threadId'], 't1')
            self.assertEqual(out['usage']['input_tokens'], 12)
            self.assertEqual(steps[0][0], '코드 분석')

    def test_failure_and_nonzero_not_success(self):
        for behavior in ["print('{\"type\":\"turn.failed\",\"error\":{\"message\":\"no auth\"}}')",
                         "print('{\"type\":\"turn.completed\"}'); sys.exit(1)"]:
            with tempfile.TemporaryDirectory() as tmp:
                binary = self.fake(tmp, behavior)
                with patch.object(codex_runner, 'executable', return_value=binary):
                    with self.assertRaises(RuntimeError):
                        codex_runner.run('p', tmp, tmp + '/log', 5)

    def test_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = self.fake(tmp, 'time.sleep(30)')
            with patch.object(codex_runner, 'executable', return_value=binary):
                with self.assertRaisesRegex(RuntimeError, '초과'):
                    codex_runner.run('p', tmp, tmp + '/log', 0.1)

    def test_schema_recurses_without_mutating(self):
        original = server.suggest_schema()
        strict = codex_runner.strict_schema(original)
        self.assertNotIn('additionalProperties', original)
        self.assertFalse(strict['properties']['items']['items']['properties']['evidence']['items']['additionalProperties'])

    def test_job_routes_snapshot_and_claude_preserved(self):
        with patch.object(server, 'current_engine', return_value='claude'), \
             patch.object(server, 'run_codex_job') as run:
            job = {'engine': 'codex'}
            server.run_job(job)
            run.assert_called_once_with(job)
        with patch.object(server, 'run_codex_suggest') as run:
            server.run_suggest('scope', 'codex')
            run.assert_called_once_with('scope')

    def test_analysis_saved_and_no_git_preparation(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {'JIRA_EMAIL':'e','JIRA_API_TOKEN':'secret','JIRA_BASE_URL':'https://example.atlassian.net'}
            with patch.multiple(server, RUNS=tmp, ANALYSIS=tmp), \
                 patch.object(server.jf, 'load_config', return_value=cfg), \
                 patch.object(server.jf, 'request', return_value={'fields':{'summary':'ticket'}}), \
                 patch.object(server.jf, 'download_images', return_value=[]), \
                 patch.object(server, 'git', return_value=Mock(stdout='main')), \
                 patch.object(server, 'prepare_codex_branch') as branch, \
                 patch.object(server, 'stash_leftovers') as stash, \
                 patch.object(codex_runner, 'run', return_value={'message':'분석 결과','usage':{},'threadId':'t'}) as run:
                server.run_codex_job({'key':'TEST-1','url':'https://example.atlassian.net/browse/TEST-1','mode':'analyze'})
                self.assertEqual(server.work_state['status'], 'done')
                self.assertIn('분석 결과', Path(tmp, 'TEST-1.md').read_text())
                self.assertFalse(run.call_args.kwargs['writable'])
                branch.assert_not_called()
                stash.assert_not_called()

    def test_work_record_and_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = {k: ([] if v['type']=='array' else '') for k,v in server.CODEX_WORK_SCHEMA['properties'].items()}
            report.update(status='blocked', kind='APP', message='결정 필요', note='모호함')
            server.validate_codex_report(report)
            with patch.multiple(server, WORKLOG=tmp, SUGGESTIONS=tmp+'/suggestions.json'):
                server.save_codex_worklog({'key':'TEST-2','url':'url'}, 'title','feature/TEST-2',report)
            record = json.loads(Path(tmp, 'TEST-2.json').read_text())
            self.assertEqual(record['status'], 'blocked')
            self.assertEqual(record['commits'], [])

    def test_suggest_merges_structured_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.multiple(server, RUNS=tmp, SUGGESTIONS=tmp+'/suggestions.json'), \
                 patch.object(codex_runner, 'run', return_value={'data':{'items':[{'title':'test','evidence':[{'file':'a','line':1}]}]},'usage':{},'threadId':'t'}):
                server.run_codex_suggest('scope')
                self.assertEqual(server.run_state['status'], 'done')
                self.assertEqual(len(server.run_state['added']), 1)

if __name__ == '__main__':
    unittest.main()
