from email.policy import default
import re
from attr import fields
import click
import json
from taskw import TaskWarrior

from jira import JIRA
import subprocess

# jira = JIRA('https://odahub.atlassian.com')


def duration_to_seconds(duration_str):
    match = re.match(
        (r'P((?P<years>\d+)Y)?((?P<months>\d+)M)?((?P<weeks>\d+)W)?'
         r'((?P<days>\d+)D)?'
         r'T((?P<hours>\d+)H)?((?P<minutes>\d+)M)?((?P<seconds>\d+)S)?'),
        duration_str
    ).groupdict()
    return int(match['years'] or 0)*365*24*3600 + \
        int(match['months'] or 0)*30*24*3600 + \
        int(match['weeks'] or 0)*7*24*3600 + \
        int(match['days'] or 0)*24*3600 + \
        int(match['hours'] or 0)*3600 + \
        int(match['minutes'] or 0)*60 + \
        int(match['seconds'] or 0)

@click.group()
@click.option('-p', '--project', default="VS")
@click.pass_obj
def cli(obj, project):
    obj['project'] = project
    obj['auth_jira'] = JIRA('https://odahub.atlassian.net', 
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
    proj = obj['project']
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

    for issue in jira.search_issues(f'project={proj} {extra_filter} order by created desc ', maxResults=False):
        print_issue(issue, long)


# issue = jira.issue('JRA-9')
# print(issue.fields.project.key)            # 'JRA'
# print(issue.fields.issuetype.name)         # 'New Feature'
# print(issue.fields.reporter.displayName)   


            
@cli.command()
@click.option('-i', '--task-id', type=int)
@click.option("-l", "--long", is_flag=True)
@click.option("-U", "--allow-update", is_flag=True)
@click.pass_obj
def push(obj, task_id, long, allow_update):
    proj = obj['project']
    jira = obj['auth_jira']

    # print(json.dumps(jira.createmeta(
    #                 projectIds=[10001]
    #             ), 
    #         indent=4, 
    #         sort_keys=True))

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
                print('issuetype:', issuetype)

        # tw_label = f"TaskWarrior:{task['id']}"

        existing_issues = [i for i in jira.search_issues(f'project={proj} AND TaskWarriorID = {taskid}')]

        if len(existing_issues) > 1:
            print("found many!", taskid, existing_issues)            
            raise NotImplementedError

        elif len(existing_issues) == 1:
            print("found:", taskid, existing_issues)            

            if not allow_update:
                print("skipping updates!")
                continue

            issue = existing_issues[0]
                        
        else:
            print("NOT found, will create")
            issue = jira.create_issue(
                    summary=task['description'],
                    project=proj,
                    customfield_10035 = task['id'],            
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
                    labels=None,
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