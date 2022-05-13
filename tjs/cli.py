import os
import pathlib
import pickle
import re
import time
from typing import Optional, Any, Dict
import click
import json
import logging
from taskw import TaskWarrior

from jira import JIRA
from jira.resources import Issue
import subprocess

from tjs.utils import duration_to_seconds

logger = logging.getLogger(__name__)

class TaskWarriorJIRA(JIRA):
    # overrides to assume project

    def __init__(self, *args, project_name, reset_cache, **kwargs):
        super().__init__(*args, **kwargs)

        self.project_name = project_name

        if reset_cache:
            self.reset_cache()
        else:
            self.load_cache()

    def search_issues(self, jql_str: str, *args, **kwargs):
        return super().search_issues(f"project={self.project_name} AND " + jql_str, *args, **kwargs)

    def create_issue(self, taskid: int, fields: Optional[Dict[str, Any]] = None, prefetch: bool = True, **fieldargs) -> Issue:        
        return super().create_issue(fields, 
                                    prefetch,
                                    project=self.project_name,
                                    customfield_10035 = taskid,
                                    **fieldargs)            

    # -----

    @property
    def cache_fn(self):
        return os.path.join(os.getenv('HOME', '/tmp/'), ".cache/tw-jira-sync.pickle")

    def load_cache(self):        
        try:
            self.cache_by_taskid = pickle.load(open(self.cache_fn, "rb"))
        except Exception as e:
            self.cache_by_taskid = {}

    def reset_cache(self):
        self.cache_by_taskid = {}
        self.write_cache()

    def write_cache(self):        
        os.makedirs(os.path.dirname(self.cache_fn), exist_ok=True)
        pickle.dump(self.cache_by_taskid, open(self.cache_fn, "wb"))
    

    def issue_for_taskid(self, taskid: int, use_cache=False):
        logger.debug('will find issue_for_taskid')
        if use_cache:
            if taskid in self.cache_by_taskid:
                logger.debug("found in cache: %s, %s", taskid, self.cache_by_taskid[taskid])            
                return self.cache_by_taskid[taskid]
                
        issues = [i for i in self.search_issues(f'TaskWarriorID = {taskid}')]

        if len(issues) > 1:
            print("found many!", taskid, issues)            
            raise NotImplementedError
        elif len(issues) == 0:
            print("found none!", taskid, issues)            
            return None
        else:
            print("found this:", taskid, issues)            
            self.cache_by_taskid[taskid] = issues[0]
            self.write_cache()
            return issues[0]


@click.group()
@click.option('-p', '--project', default="VS")
@click.option('-v', '--verbose', is_flag=True)
@click.option('-R', '--reset-cache', is_flag=True)
@click.pass_obj
def cli(obj, project, verbose, reset_cache):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)

    obj['auth_jira'] = TaskWarriorJIRA(
                            'https://odahub.atlassian.net', 
                            project_name=project,
                            reset_cache=reset_cache,
                            basic_auth=('vladimir.savchenko@gmail.com',
                                        subprocess.check_output(['pass', 'jiracould']).decode().strip()))
                                    


def print_issue(issue, long):
    print('\033[31m{}\033[0m: \033[33m{}\033[0m'.format(issue.key, issue.fields.summary))

    if long:
        for k in dir(issue.fields):
            if not k.startswith("_"):
                v = getattr(issue.fields, k)
                print('    \033[36m{}\033[0m: {}'.format(k, v))

        for issue_link in issue.fields.issuelinks:
            print(f"{issue_link}: {issue_link.type} {issue_link.outwardIssue}")
            # for k in dir(issue_link):
            #     print(f" > {k} {getattr(issue_link, k)}")
            
@cli.command()
@click.option('-i', '--task-id', type=int, default=None)
@click.option("-l", "--long", is_flag=True)
@click.pass_obj
def list(obj, long, task_id):
    jira = obj['auth_jira']

    # Search returns first 50 results, `maxResults` must be set to exceed this
    # issues_in_proj = jira.search_issues(f'project={proj}')
    # all_proj_issues_but_mine = jira.search_issues(f'project={proj} and assignee != currentUser()')

    # my top 5 issues due by the end of the week, ordered by priority
    # oh_crap = jira.search_issues('assignee = currentUser() and due < endOfWeek() order by priority desc', maxResults=5)

    # Summaries of my last 3 reported issues

    extra_filter = ''
    if task_id is not None:
        extra_filter =  f'AND TaskWarriorID = {task_id}'

    for issue in jira.search_issues(f'{extra_filter} order by created desc ', maxResults=False):
        print_issue(issue, long)


# issue = jira.issue('JRA-9')
# print(issue.fields.project.key)            # 'JRA'
# print(issue.fields.issuetype.name)         # 'New Feature'
# print(issue.fields.reporter.displayName)   


            
@cli.command("push")
@click.option('-i', '--task-id', type=int)
@click.option("-l", "--long", is_flag=True)
@click.option("-U", "--allow-update", is_flag=True)
@click.option("-1", "--run-once", is_flag=True)
@click.pass_obj
def _push(obj, task_id, long, allow_update, run_once):
    jira = obj['auth_jira']

    # print(json.dumps(jira.createmeta(
    #                 projectIds=[10001]
    #             ), 
    #         indent=4, 
    #         sort_keys=True))

    while True:
        push(jira, task_id, long, allow_update)

        if run_once:
            break
        else:
            logger.info("sleeping...")
            for i in range(60):
                time.sleep(1)
                print(".", end="", flush=True)
                


def push(jira: TaskWarriorJIRA, task_id, long, allow_update):
    w = TaskWarrior()
    tasks = w.load_tasks()
    # for k, v in tasks.items():
    #     print(k)
    for task in tasks['pending']:
        # print(task)
        taskid = task["id"]

        if task_id is not None and task_id != taskid:
            continue

        issuetype = 'Task'
        for issuetype_key in ['redminetracker']:
            if issuetype_key in task:
                issuetype = task[issuetype_key]        
                logger.debug('deduced issuetype %s from %s', issuetype_key, issuetype)

                
        issue = jira.issue_for_taskid(taskid, use_cache=not allow_update)
                
        if issue is not None:
            if not allow_update:
                logger.debug("skipping updates!")
                continue
                
        else:
            print("NOT found, will create")
            issue = jira.create_issue(
                    taskid=taskid,
                    summary=task['description'],                    
                    issuetype={'name': issuetype},
                )

            print('created: {}: {}'.format(issue.key, issue.fields.summary))
        

        # title 

        for title_key in ['redminesubject', 'gitlabtitle']:
            if title_key in task:
                print('updating title')
                task['description'] = task[title_key]

        # base


        fields = dict(
                    summary=task['description'],
                    description="\n".join([f"{k}: {v}" for k, v in task.items()]), 
                    labels=None
                )

        # estimate

        estimate_s = None
        for estimate_key in ['redmineestimatedhours']:
            if estimate_key in task:
                estimate_s = duration_to_seconds(task[estimate_key])
                fields['timetracking'] = {
                    "originalEstimate": f"{int(estimate_s/60.)}m"
                }                

        
        issue.update(**fields) 

        # tags

        tags = task.get('tags', [])

        for tag_field in ['project', 'gitlabnamespace']:
            if tag_field in task:
                tags.append(task[tag_field])

        print("updating labels", tags)

        
        for tag in tags:
            issue.add_field_value(
                'labels', tag
            )

        # urls

        for url_field, title in [
                ('redmineurl', "Redmine URL")
            ]:
            if url_field in task:
                print('adding', task[url_field])
                jira.add_simple_link(issue, {
                    "url": task[url_field],
                    "title": title
                })

        print_issue(issue, long)
            


# issue = jira.issue('JRA-9')
# print(issue.fields.project.key)            # 'JRA'
# print(issue.fields.issuetype.name)         # 'New Feature'
# print(issue.fields.reporter.displayName)   



if __name__ == "__main__":
    cli(obj={})