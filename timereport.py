import re
import sys
import typing
from argparse import ArgumentParser
from collections import defaultdict
from datetime import date, timedelta

from git import Repo


class Work(typing.NamedTuple):
    task: str
    date: date
    hours: float


def get_parser() -> ArgumentParser:
    parser = ArgumentParser()
    parser.add_argument('paths', nargs='*')
    parser.add_argument('--email', nargs='*')
    parser.add_argument('--task', default=r'[A-Z]{1,8}\-?[0-9]{1,8}')
    parser.add_argument('--group-by', default='day', choices=('day', 'week', 'month'))
    parser.add_argument('--delta', type=int, default=30)
    parser.add_argument('--hours', type=int, default=8)
    parser.add_argument('--sep', default='\t')
    return parser


CommitsType = typing.Dict[date, typing.Dict[int, typing.List[str]]]
WorksType = typing.List[Work]


def collect_commits(
    repo: Repo,
    emails: typing.List[str],
    rex_task: typing.Pattern,
    delta: timedelta,
    today: date,
) -> CommitsType:
    commits: CommitsType = defaultdict(lambda: defaultdict(list))
    for commit in repo.iter_commits():
        if commit.author.email not in emails:
            continue
        if today - commit.authored_datetime.date() > delta:
            continue
        match = rex_task.search(commit.message)
        if match is None:
            continue
        task = match.group(0)
        cdate = commit.authored_datetime.date()
        chour = commit.authored_datetime.hour
        commits[cdate][chour].append(task)
    return commits


def calculate_works(commits: CommitsType, hours: int) -> WorksType:
    works: WorksType = []
    for cdate, day in commits.items():
        hour_ratio = hours / len(day)
        day_summary: typing.Dict[str, float] = defaultdict(int)
        for tasks in day.values():
            task_ratio = hour_ratio / len(tasks)
            for task in tasks:
                day_summary[task] += task_ratio
        for task, thours in day_summary.items():
            works.append(Work(task=task, hours=thours, date=cdate))
    return works


def report(works: WorksType, group_by: str) -> typing.Iterator[typing.Tuple[str, str, str]]:
    grouped: typing.Dict[str, WorksType] = defaultdict(list)
    for work in works:
        if group_by == 'day':
            key = str(work.date)
        elif group_by == 'week':
            key = '{}-{}-{}'.format(
                work.date.year,
                work.date.month,
                work.date.isocalendar()[1],
            )
        elif group_by == 'month':
            key = '{}-{}'.format(
                work.date.year,
                work.date.month,
            )
        else:
            raise RuntimeError('unsupported group_by', group_by)
        grouped[key].append(work)
    for key, subworks in sorted(grouped.items()):
        for work in subworks:
            yield key, work.task, str(round(work.hours))


def merge_commits(total: CommitsType, new: CommitsType) -> CommitsType:
    result: CommitsType = defaultdict(lambda: defaultdict(list))
    for cdate, chours in total.items():
        for chour, tasks in chours.items():
            result[cdate][chour].extend(tasks)
    for cdate, chours in new.items():
        for chour, tasks in chours.items():
            result[cdate][chour].extend(tasks)
    return result


def main(argv: typing.List[str]) -> int:
    parser = get_parser()
    args = parser.parse_args(args=argv)

    all_commits: CommitsType = dict()
    for path in args.paths:
        repo = Repo(path)
        emails = args.email
        if not emails:
            email = repo.config_reader().get_value('user', 'email')
            emails = [email]
        repo_commits = collect_commits(
            repo=repo,
            emails=emails,
            rex_task=re.compile(args.task),
            delta=timedelta(days=args.delta),
            today=date.today(),
        )
        all_commits = merge_commits(all_commits, repo_commits)
    works = calculate_works(
        commits=all_commits,
        hours=args.hours,
    )
    lines = report(works=works, group_by=args.group_by)
    for line in lines:
        print(args.sep.join(line))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
