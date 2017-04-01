#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Gitline
# by Markus Engelbrecht
#
# Credits
# * git-radar (https://github.com/michaeldfallen/git-radar)
# * gitHUD (https://github.com/gbataille/gitHUD)
#
# MIT License
# -------------------------------------------------------------------------------

import argparse
import subprocess
from string import Template
from threading import Thread

import os


def parse_repository():
    def execute(command):
        with open(os.devnull) as DEVNULL:
            return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=DEVNULL,
                                    universal_newlines=True).communicate()[0]

    repo = dict(
        directory="", branch="", remote="", remote_tracking_branch="", hash="",
        local_commits_to_pull=0, local_commits_to_push=0, remote_commits_to_pull=0, remote_commits_to_push=0,
        staged_added=0, staged_modified=0, staged_deleted=0, staged_renamed=0, staged_copied=0,
        unstaged_modified=0, unstaged_deleted=0, untracked=0, unmerged=0, stashes=0
    )
    repo['directory'] = execute(['git', 'rev-parse', '--show-toplevel']).rstrip()
    if not repo['directory']:
        return None

    def execute_tasks(*args):
        threads = [Thread(target=task) for task in args]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    def branch():
        repo['branch'] = execute(['git', 'symbolic-ref', '--short', 'HEAD']).rstrip()

    def hash():
        repo['hash'] = execute(['git', 'rev-parse', '--short', 'HEAD']).rstrip()

    def stashes():
        repo['stashes'] = execute(['git', 'stash', 'list']).count('\n')

    def status():
        for code in [x[0:2] for x in execute(['git', 'status', '-z']).split('\0')]:
            if code in ["A ", "AD", "AM"]:
                repo['staged_added'] += 1
            if code in [" M", "AM", "CM", "RM"]:
                repo['unstaged_modified'] += 1
            if code in ["M ", "MD", "MM"]:
                repo['staged_modified'] += 1
            if code in [" D", "AD", "CD", "MD", "RD"]:
                repo['unstaged_deleted'] += 1
            if code in ["D ", "DM"]:
                repo['staged_deleted'] += 1
            if code in ["R ", "RD", "RM"]:
                repo['staged_renamed'] += 1
            if code in ["C ", "CA", "CD", "CM", "CR"]:
                repo['staged_copied'] += 1
            if code in ["AA", "AU", "DD", "DU", "UU", "UA", "UD"]:
                repo['unmerged'] += 1
            if code == "??":
                repo['untracked'] += 1

    def commits_to_pull(source, dest):
        try:
            return int(
                execute(['git', 'rev-list', '--no-merges', '--left-only', '--count', source + '...' + dest]).rstrip())
        except ValueError:
            return 0

    def commits_to_push(source, dest):
        try:
            return int(
                execute(['git', 'rev-list', '--no-merges', '--right-only', '--count', source + '...' + dest]).rstrip())
        except ValueError:
            return 0

    def local_commits_to_pull():
        repo['local_commits_to_pull'] = commits_to_pull(repo['remote_tracking_branch'], 'HEAD')

    def local_commits_to_push():
        repo['local_commits_to_push'] = commits_to_push(repo['remote_tracking_branch'], 'HEAD')

    def remote_commits_to_pull():
        repo['remote_commits_to_pull'] = commits_to_pull('origin/master', repo['remote_tracking_branch'])

    def remote_commits_to_push():
        repo['remote_commits_to_push'] = commits_to_push('origin/master', repo['remote_tracking_branch'])

    execute_tasks(status, branch, stashes, hash)
    repo['remote'] = execute(['git', 'config', '--get', 'branch.' + repo['branch'] + '.remote']).rstrip()
    repo['remote_tracking_branch'] = execute(
        ['git', 'config', '--get', 'branch.' + repo['branch'] + '.merge']).rstrip().replace('refs/heads',
                                                                                            repo['remote'], 1)
    if execute(['git', 'merge-base', repo['remote_tracking_branch'], 'origin/master']).rstrip():
        execute_tasks(local_commits_to_pull, local_commits_to_push, remote_commits_to_pull, remote_commits_to_push)
    else:
        execute_tasks(local_commits_to_pull, local_commits_to_push)
    return repo


def build_prompt(repo):
    data = dict(
        gray='\033[30m', red='\033[31m', green='\033[32m', yellow='\033[33m', blue='\033[34m',
        magenta='\033[35m', cyan='\033[36m', white='\033[37m', reset='\033[0m'
    )
    data.update(repo)

    def env_str(s, default):
        return os.getenv('GITLINE_' + s, default)

    def expand(*args):
        return ''.join(Template(fmt).substitute(data) for cond, fmt in args if cond)

    def choose(formats, *args):
        return expand((True, formats[sum(1 << i for i, v in enumerate(reversed(args)) if v)]))

    parts = [
        expand((True, env_str('REPO_INDICATOR', '${reset}ᚴ'))),
        expand((not repo['remote_tracking_branch'], env_str('NO_TRACKED_UPSTREAM', 'upstream ${red}⚡${reset}'))),
        choose(['',
                env_str('REMOTE_COMMITS_PUSH', '𝘮 ${green}←${reset}${remote_commits_to_push}'),
                env_str('REMOTE_COMMITS_PULL', '𝘮 ${red}→${reset}${remote_commits_to_pull}'),
                env_str('REMOTE_COMMITS_PUSH_PULL',
                        '𝘮 ${remote_commits_to_pull} ${yellow}⇄${reset} ${remote_commits_to_push}')],
               repo['remote_commits_to_pull'], repo['remote_commits_to_push']),
        choose([env_str('DETACHED', '${red}detached@${hash}${reset}'), env_str('BRANCH', '${branch}')], repo['branch']),
        choose(['',
                env_str('LOCAL_COMMITS_PUSH', '${local_commits_to_push}${green}↑${reset}'),
                env_str('LOCAL_COMMITS_PULL', '${local_commits_to_pull}${red}↓${reset}'),
                env_str('LOCAL_COMMITS_PUSH_PULL', '${local_commits_to_pull} ${yellow}⥯${reset} ${local_commits_to_push}')],
               repo['local_commits_to_pull'], repo['local_commits_to_push']),
        expand((repo['staged_added'], env_str('STAGED_ADDED', '${staged_added}${green}A${reset}')),
               (repo['staged_modified'], env_str('STAGED_MODIFIED', '${staged_modified}${green}M${reset}')),
               (repo['staged_deleted'], env_str('STAGED_DELETED', '${staged_deleted}${green}D${reset}')),
               (repo['staged_renamed'], env_str('STAGED_RENAMED', '${staged_renamed}${green}R${reset}')),
               (repo['staged_copied'], env_str('STAGED_COPIED', '${staged_copied}${green}C${reset}'))),
        expand((repo['unstaged_modified'], env_str('UNSTAGED_MODIFIED', '${unstaged_modified}${red}M${reset}')),
               (repo['unstaged_deleted'], env_str('UNSTAGED_DELETED', '${unstaged_deleted}${red}D${reset}'))),
        expand((repo['untracked'], env_str('UNTRACKED', '${untracked}${white}A${reset}'))),
        expand((repo['unmerged'], env_str('UNMERGED', '${unmerged}${yellow}U${reset}'))),
        expand((repo['stashes'], env_str('STASHES', '${stashes}${yellow}≡${reset}')))
    ]

    return ' '.join(filter(bool, parts))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', nargs='?', help='directory to display git info for')
    arguments = parser.parse_args()
    if arguments.directory:
        os.chdir(arguments.directory)

    r = parse_repository()
    if r:
        prompt = build_prompt(r)
        print(prompt)
