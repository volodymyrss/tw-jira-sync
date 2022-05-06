from email.policy import default
import click
import json
from taskw import TaskWarrior

from jira import JIRA
import subprocess

# jira = JIRA('https://odahub.atlassian.com')



@click.group()
@click.option('-p', '--project', default="VS")
@click.pass_obj
def cli(obj, project):
    obj['project'] = project
    obj['auth_jira'] = JIRA('https://odahub.atlassian.net', 
                            basic_auth=('vladimir.savchenko@gmail.com',
                                        subprocess.check_output(['pass', 'jiracould']).decode().strip()))
            
@cli.command()
@click.option("-l", "--long", is_flag=True)
@click.pass_obj
def list(obj, long):
    proj = obj['project']
    jira = obj['auth_jira']

    # Search returns first 50 results, `maxResults` must be set to exceed this
    # issues_in_proj = jira.search_issues(f'project={proj}')
    # all_proj_issues_but_mine = jira.search_issues(f'project={proj} and assignee != currentUser()')

    # my top 5 issues due by the end of the week, ordered by priority
    # oh_crap = jira.search_issues('assignee = currentUser() and due < endOfWeek() order by priority desc', maxResults=5)

    # Summaries of my last 3 reported issues
    for issue in jira.search_issues(f'project={proj} order by created desc', maxResults=False):
        print('{}: {}'.format(issue.key, issue.fields.summary))

        if long:
            for k in dir(issue.fields):
                if not k.startswith("_"):
                    print('    {}: {}'.format(k, getattr(issue.fields, k)))

# issue = jira.issue('JRA-9')
# print(issue.fields.project.key)            # 'JRA'
# print(issue.fields.issuetype.name)         # 'New Feature'
# print(issue.fields.reporter.displayName)   


            
@cli.command()
@click.option('-i', '--task-id', type=int)
@click.pass_obj
def push(obj, task_id):
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

        # tw_label = f"TaskWarrior:{task['id']}"

        existing_issues = [i for i in jira.search_issues(f'project={proj} AND TaskWarriorID = {taskid}')]

        if len(existing_issues) > 1:
            print("found many!", taskid, existing_issues)            
            raise NotImplementedError

        elif len(existing_issues) == 1:
            print("found:", taskid, existing_issues)            
            issue = existing_issues[0]
            
            issue.update(labels=None) #",".join(task['tags']))

            tags = task.get('tags', [])

            for tag_field in ['project', 'gitlabnamespace']:
                if tag_field in task:
                    tags.append(task[tag_field])



            print("updating labels", tags)

            for tag in tags:
                issue.add_field_value(
                    'labels', tag
                )

            if 'gitlabtitle' in task:
                print('updating title')
                issue.update(summary=task['gitlabtitle'])

            for url_field in ['redmineurl']:
                if url_field in task:
                    issue.add_field_value('issuelinks', task[url_field])
            

        else:
            print("NOT found, will create")
            issue = jira.create_issue(
                project=proj, 
                summary=task['description'],
                description="\n".join([f"{k}: {v}" for k, v in task.items()]), 
                issuetype={'name': 'Task'},
                customfield_10035 = task['id'],            
                )

            print('created: {}: {}'.format(issue.key, issue.fields.summary))


# issue = jira.issue('JRA-9')
# print(issue.fields.project.key)            # 'JRA'
# print(issue.fields.issuetype.name)         # 'New Feature'
# print(issue.fields.reporter.displayName)   



if __name__ == "__main__":
    cli(obj={})