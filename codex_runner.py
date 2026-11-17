"""Non-interactive Codex transport. No Jira credentials or dashboard writes here."""
import copy
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading


def executable():
    candidates = [shutil.which('codex'), os.path.expanduser('~/.local/bin/codex'),
                  '/opt/homebrew/bin/codex', '/usr/local/bin/codex',
                  '/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex',
                  '/Applications/Codex.app/Contents/Resources/codex']
    return next((p for p in candidates if p and os.path.isfile(p) and os.access(p, os.X_OK)), None)


def strict_schema(schema):
    schema = copy.deepcopy(schema)
    def visit(node):
        if not isinstance(node, dict):
            return
        if node.get('type') == 'object':
            node['additionalProperties'] = False
            node['required'] = list(node.get('properties', {}))
        for value in node.values():
            if isinstance(value, dict):
                visit(value)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
    visit(schema)
    return schema


def run(prompt, cwd, log_path, timeout, *, writable=False, schema=None, images=(), on_step=None):
    binary = executable()
    if not binary:
        raise RuntimeError('Codex CLI를 찾을 수 없습니다. 설치 후 서버를 다시 시작하세요.')
    state = {'message': '', 'usage': {}, 'threadId': None}
    completed = False
    failure = None
    expired = threading.Event()
    with tempfile.TemporaryDirectory(prefix='devflow-codex-') as tmp:
        output = os.path.join(tmp, 'result.txt')
        cmd = [binary, 'exec', '--json', '--ignore-user-config',
               '-c', 'approval_policy="never"',
               '--sandbox', 'workspace-write' if writable else 'read-only',
               '-C', cwd, '-o', output]
        if schema is not None:
            path = os.path.join(tmp, 'schema.json')
            with open(path, 'w', encoding='utf-8') as fp:
                json.dump(strict_schema(schema), fp, ensure_ascii=False)
            cmd += ['--output-schema', path]
        for path in images:
            cmd += ['--image', path]
        cmd += ['-']
        # Prompt via a file-backed stdin avoids argv size limits and pipe deadlocks.
        with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as inp, \
                open(log_path, 'w', encoding='utf-8') as log, \
                open(log_path + '.stderr', 'w', encoding='utf-8') as err:
            inp.write(prompt)
            inp.seek(0)
            env = {k: v for k, v in os.environ.items() if k not in ('JIRA_API_TOKEN', 'JIRA_EMAIL')}
            proc = subprocess.Popen(cmd, cwd=cwd, stdin=inp, stdout=subprocess.PIPE,
                                    stderr=err, text=True, env=env, start_new_session=True)
            def kill_group():
                expired.set()
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            timer = threading.Timer(timeout, kill_group)
            timer.start()
            try:
                for line in proc.stdout:
                    log.write(line)
                    log.flush()
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    kind = event.get('type')
                    if kind == 'thread.started':
                        state['threadId'] = event.get('thread_id')
                    elif kind == 'turn.completed':
                        completed = True
                        state['usage'] = event.get('usage', {})
                    elif kind in ('turn.failed', 'error'):
                        failure = event.get('error') or event.get('message') or kind
                    item = event.get('item') or {}
                    if kind == 'item.completed' and item.get('type') == 'agent_message':
                        state['message'] = item.get('text', '')
                    if on_step and kind == 'item.started' and item.get('type') == 'command_execution':
                        command = item.get('command', '')
                        on_step('빌드 확인' if 'gradlew' in command else '코드 분석', command[:200])
                    if on_step and kind == 'item.completed' and item.get('type') == 'file_change':
                        for change in item.get('changes', []):
                            on_step('코드 수정', change.get('path', ''))
                proc.wait()
            finally:
                timer.cancel()
                if proc.poll() is None:
                    kill_group()
                proc.wait()
                proc.stdout.close()
        if expired.is_set():
            raise RuntimeError(f'{timeout // 60}분 초과로 Codex 실행을 중단했습니다')
        if proc.returncode or failure or not completed:
            raise RuntimeError(f'Codex 실행 실패 (종료 코드 {proc.returncode}, {failure or "완료 이벤트 없음"}). 로그: {log_path}.stderr')
        if os.path.exists(output):
            with open(output, encoding='utf-8') as fp:
                state['message'] = fp.read().strip()
        if not state['message']:
            raise RuntimeError('Codex가 최종 결과를 반환하지 않았습니다')
        if schema is not None:
            state['data'] = json.loads(state['message'])
        return state
