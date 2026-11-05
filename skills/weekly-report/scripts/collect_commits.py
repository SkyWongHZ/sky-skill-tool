#!/usr/bin/env python3
"""Read configured local refs + GitLab branches; save evidence, never change refs."""
import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo


def run(args, cwd=None, timeout=45):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                            env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    if result.returncode:
        # Don't echo credential-bearing remote URLs or raw server errors.
        raise RuntimeError(f'{args[0]} {args[1]} failed (exit {result.returncode})')
    return result.stdout


def collect(config, start, end):
    git = config.get('git_executable', 'git')
    rows = []
    for repo in config['repositories']:
        path = repo['path']
        entry = {'project': repo['project'], 'path': path, 'errors': [], 'commits': []}
        commits = {}

        def belongs(name, email):
            return name in config['author_names'] or email.lower() in {
                e.lower() for e in config['author_emails']}

        try:
            heads = [line[5:] for line in run([git, '-C', path, 'worktree', 'list', '--porcelain']).splitlines()
                     if line.startswith('HEAD ')]
            raw = run([git, '-C', path, 'log', '--all', *heads,
                       f'--since-as-filter={start}', f'--until={end}',
                       '--format=%H%x00%P%x00%an%x00%ae%x00%aI%x00%cI%x00%B%x00%x1e'])
            for record in raw.split('\x1e'):
                parts = record.strip('\n').split('\x00')
                if len(parts) < 8:
                    continue
                sha, parents, name, email, authored, committed, message = parts[:7]
                if not belongs(name, email):
                    continue
                commits[sha] = {'hash': sha, 'parents': parents.split(), 'author_name': name,
                                'author_email': email, 'authored_at': authored,
                                'committed_at': committed, 'message': message.strip(),
                                'local': True, 'gitlab': False}
            entry['local_ok'] = True
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
            entry['local_ok'] = False
            entry['errors'].append(f'local: {exc}')

        remote_ok = True
        try:
            for page in range(1, 101):
                query = urlencode({'all': 'true', 'since': start, 'until': end,
                                   'per_page': 100, 'page': page})
                endpoint = f"projects/{quote(repo['project'], safe='')}/repository/commits?{query}"
                data = json.loads(run(['glab', 'api', endpoint, '--hostname', config['gitlab_host']]))
                if not isinstance(data, list):
                    raise RuntimeError('Unexpected GitLab response')
                for commit in data:
                    if not belongs(commit['author_name'], commit['author_email']):
                        continue
                    sha = commit['id']
                    if sha not in commits:
                        commits[sha] = {'hash': sha, 'parents': commit['parent_ids'],
                                        'author_name': commit['author_name'], 'author_email': commit['author_email'],
                                        'authored_at': commit['authored_date'], 'committed_at': commit['committed_date'],
                                        'message': commit['message'].strip(), 'local': False}
                    commits[sha]['gitlab'] = True
                if len(data) < 100:
                    break
            else:
                raise RuntimeError('GitLab pagination limit reached; narrow time window')
        except (RuntimeError, subprocess.TimeoutExpired, OSError, ValueError, KeyError) as exc:
            remote_ok = False
            entry['errors'].append(f'gitlab: {exc}')
        entry['remote_ok'] = remote_ok

        for commit in commits.values():
            commit['merge'] = len(commit['parents']) > 1
            try:
                if commit['local']:
                    commit['files'] = run([git, '-c', 'core.quotepath=false', '-C', path, 'show', '--format=', '--name-only',
                                           commit['hash']]).splitlines()
                else:
                    endpoint = f"projects/{quote(repo['project'], safe='')}/repository/commits/{commit['hash']}/diff"
                    data = json.loads(run(['glab', 'api', endpoint, '--hostname', config['gitlab_host']]))
                    commit['files'] = [d['new_path'] for d in data]
                    commit['diff_scope'] = 'GitLab default diff page; fetch more if needed'
            except (RuntimeError, subprocess.TimeoutExpired, OSError, ValueError, KeyError) as exc:
                entry['errors'].append(f"files {commit['hash'][:10]}: {exc}")
            commit['availability'] = ('GitLab已可见' if commit['gitlab'] else
                                      '本地可见，GitLab本次查询未见' if remote_ok else
                                      '本地可见，远端查询失败')
        entry['commits'] = sorted(commits.values(), key=lambda c: (c['committed_at'], c['hash']))
        rows.append(entry)
        print(f"{repo['project']}: {len(commits)} commits, {len(entry['errors'])} errors", flush=True)
    return {'start': start, 'end': end, 'timezone': config['timezone'], 'repositories': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--start', required=True, help='ISO datetime with timezone')
    parser.add_argument('--end', help='ISO datetime with timezone, default now')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    end = args.end or dt.datetime.now(ZoneInfo(config['timezone'])).isoformat(timespec='seconds')
    start_dt, end_dt = dt.datetime.fromisoformat(args.start), dt.datetime.fromisoformat(end)
    if start_dt.tzinfo is None or end_dt.tzinfo is None or start_dt > end_dt:
        parser.error('start/end must have timezone and start <= end')
    result = collect(config, args.start, end)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Evidence is immutable; repeat runs get a new output filename.
    with output.open('x') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(f'Evidence: {output}')
    if any(r['errors'] for r in result['repositories']):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
