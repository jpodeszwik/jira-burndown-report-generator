#!/usr/bin/env python3
import requests
import sys
from requests.auth import HTTPBasicAuth
from itertools import groupby
import dateutil.parser
from datetime import timedelta

api_root = sys.argv[1]
username = sys.argv[2]
password = sys.argv[3]
name = sys.argv[4]
start_date = sys.argv[5]
end_date = sys.argv[6]

auth = HTTPBasicAuth(username, password)

def find_issues_links():
  data = {'jql' : 'worklogAuthor = ' + name + ' and worklogDate > ' + start_date + ' and worklogDate < ' + end_date}
  url = api_root + '/search'
  print(url, file=sys.stderr)
  r = requests.post(url, json=data, auth=auth)
  js = r.json()
  issues = js['issues']
  return [{'key': issue['key'], 'url': issue['self']} for issue in issues]

def parse_estimations(estimations):
  developer_estimation = [estimation for estimation in estimations if estimation.startswith('Role: Developer')]
  if len(developer_estimation) > 0 and developer_estimation[0].split('(')[1].isdigit():
    return int(developer_estimation[0].split('(')[1]) / 3600

  generic_estimation = [estimation for estimation in estimations if estimation.startswith('Role: -1')]
  if len(generic_estimation) > 0:
    return int(generic_estimation[0].split('(')[1]) / 3600

  return 0

def is_in_date_range(date):
  end_date_plus_one = (dateutil.parser.parse(end_date) + timedelta(days=1)).isoformat()
  return date >= start_date and date < end_date_plus_one


def sum_times(person_logs):
  total =  sum([log['time'] for log in person_logs]) / 3600
  in_range =  sum([log['time'] for log in person_logs if is_in_date_range(log['started'])]) / 3600
  return { 'total' : total, 'other_sprint' : total > in_range * 2 }

def is_owner(people_time):
  max_time = max([people_time[k]['total'] for k in people_time])
  persons_time = people_time[name]['total']

  return max_time == persons_time

def parse_issue(issue):
  print(issue['url'], file=sys.stderr)
  r = requests.get(issue['url'], auth=auth)
  js = r.json()
  fields = js['fields']
  estimations = parse_estimations(fields['customfield_12340']) if fields['customfield_12340'] is not None else fields['timeoriginalestimate']
  worklog = fields['worklog']
  summary = fields['summary']

  if worklog['maxResults'] < worklog['total']:
      url = issue['url'] + '/worklog'
      print(url, file=sys.stderr)
      worklog = requests.get(url, auth=auth).json()

  worklogs = worklog['worklogs']
  wl = [{'person' : worklog['author']['name'], 'time': worklog['timeSpentSeconds'], 'started': worklog['started']} for worklog in worklogs]
  keyfunc = lambda x : x['person']
  wl = sorted(wl, key=keyfunc)
  groupped = groupby(wl, keyfunc)
  people_time = {person: sum_times(list(logs)) for person, logs in groupped}
  own_time = people_time[name]
  return { 'key' : issue['key'], 'summary': summary, 'estimation': estimations, 'logged': own_time['total'], 'owner': is_owner(people_time), 'other_sprint': own_time['other_sprint'] }

print('Report {} {} - {}'.format(name, start_date, end_date))

issues = find_issues_links()


parsed_issues = [parse_issue(issue) for issue in issues if issue['key'] != 'KID-1']
refinement_issues = [issue for issue in parsed_issues if 'Refinement' in issue['summary']]
refinement_work = sum([issue['logged'] for issue in refinement_issues])
print('Refinements work: {}'.format(refinement_work))
issues_without_refinements = [issue for issue in parsed_issues if 'Refinement' not in issue['summary']]
total_work = sum([issue['logged'] for issue in issues_without_refinements])
print('Total hours logged: {}'.format(total_work))

minor_work = sum([issue['logged'] for issue in issues_without_refinements if not issue['owner']])
print('Minor work: {}'.format(minor_work))

owned_issues = [issue for issue in issues_without_refinements if issue['owner'] and not issue['other_sprint']]
other_sprint = [issue for issue in issues_without_refinements if issue['owner'] and issue['other_sprint']]

total_logged = sum([issue['logged'] for issue in owned_issues])
total_estimation = sum([issue['estimation'] for issue in owned_issues])
total_burnout = total_logged - total_estimation
total_burnout_percent = total_burnout / total_estimation * 100

print('Other sprint')
for issue in other_sprint:
  burnout = issue['logged'] - issue['estimation'] if issue['estimation'] > 0 else 0
  burnout_percent = burnout / issue['estimation'] * 100 if issue['estimation'] > 0 else 0

  print('{} {} estimated {} logged {} burnout {} = {}%'.format(issue['key'], issue['summary'], int(issue['estimation']), int(issue['logged']), int(burnout), int(burnout_percent)))


print('Owned issued')

for issue in owned_issues:
  burnout = issue['logged'] - issue['estimation'] if issue['estimation'] > 0 else 0
  burnout_percent = burnout / issue['estimation'] * 100 if issue['estimation'] > 0 else 0

  print('{} {} estimated {} logged {} burnout {} = {}%'.format(issue['key'], issue['summary'], int(issue['estimation']), int(issue['logged']), int(burnout), int(burnout_percent)))

print('Total: estimated {} logged {} burnout {} = {}%'.format(int(total_estimation), int(total_logged), int(total_burnout), int(total_burnout_percent)))
