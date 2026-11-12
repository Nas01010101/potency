"""Second opinion on the agent's reasons, from a small model a maintainer can run in CI.

For an expected file the agent left alone, the checker sees the issue, the agent's diff, the lines
of that file that mention the names the diff touches, and the agent's REASON line, and answers
HOLDS (the file needs no change) or DOUBT. It talks to any OpenAI-compatible server with the
standard library only, so it runs where the report runs. Default model: Gemma 4 E4B.
"""
import json, os, re, subprocess, urllib.request

NAME = re.compile(r'\b(?:def|class)\s+([A-Za-z_]\w*)')
HUNK = re.compile(r'^@@[^@]*@@\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)', re.M)
PROMPT = """You review a code change for an open-source maintainer.

Issue (truncated):
{issue}

The contributor's diff (truncated):
{diff}

The repository ties `{path}` to the edited files ({evidence}). The contributor did not change it and wrote:
REASON: {reason}

Lines of `{path}` that mention names the diff touches:
{excerpt}

Does `{path}` really need no change for this fix to be complete? Reply with one line: HOLDS or DOUBT, then a colon and at most 25 words on why."""


def names(patch):
    """Function and class names the diff defines, changes, or sits inside."""
    out = set(HUNK.findall(patch))
    for line in patch.splitlines():
        if line[:1] in '+-' and not line.startswith(('+++', '---')):
            out |= set(NAME.findall(line))
    return sorted(out)


def excerpt(text, keys, ctx=3, cap=120):
    """Windows of ctx lines around each line mentioning a key, numbered, at most cap lines."""
    lines = text.splitlines()
    keep = sorted({j for i, l in enumerate(lines) if any(re.search(rf'\b{re.escape(k)}\b', l) for k in keys)
                   for j in range(max(0, i - ctx), min(len(lines), i + ctx + 1))})
    if not keep:
        return '(none of the changed names appear in this file; its first lines:)\n' + \
            '\n'.join(f'{i + 1}: {l}' for i, l in enumerate(lines[:40]))
    return '\n'.join(f'{i + 1}: {lines[i]}' for i in keep[:cap])


def parse(reply):
    """('HOLDS' | 'DOUBT' | 'UNPARSED', note) from the model's reply."""
    m = re.search(r'\b(HOLDS|DOUBT)\b[\s:*\-]*(.*)', reply or '')
    return (m.group(1), m.group(2).strip()[:200]) if m else ('UNPARSED', (reply or '').strip()[:200])


def ask(prompt, base=None, key=None, model=None, timeout=120):
    base = base or os.environ['CHECKER_BASE']
    body = {'model': model or os.environ.get('CHECKER_MODEL', 'gemma4-e4b'), 'temperature': 0, 'max_tokens': 120,
            'messages': [{'role': 'user', 'content': prompt}],
            'chat_template_kwargs': {'enable_thinking': False}}
    req = urllib.request.Request(base.rstrip('/') + '/v1/chat/completions', json.dumps(body).encode(),
                                 {'Content-Type': 'application/json',
                                  'Authorization': f'Bearer {key or os.environ.get("CHECKER_KEY", "")}'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)['choices'][0]['message']['content']


def check_reason(repo, base, issue, patch, path, reason, evidence, **kw):
    """(verdict, note) for one REASON line."""
    try:
        text = subprocess.run(['git', '-C', str(repo), 'show', f'{base}:{path}'], capture_output=True,
                              text=True, check=True).stdout
    except subprocess.CalledProcessError:
        text = ''
    p = PROMPT.format(issue=issue[:1500], diff=patch[:4000], path=path, evidence='; '.join(evidence),
                      reason=reason, excerpt=excerpt(text, names(patch)))
    return parse(ask(p, **kw))
