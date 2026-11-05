#!/usr/bin/env python3
"""Evaluate verified annual holiday calendars without inventing missing years."""
import argparse
import datetime as dt
import json
from pathlib import Path


def evaluate(data, day):
    def workday(date):
        year = data['years'].get(str(date.year))
        if year is None:
            return None
        stamp = date.isoformat()
        if stamp in year['makeup_workdays']:
            return True
        if any(h['start'] <= stamp <= h['end'] for h in year['holidays']):
            return False
        return date.weekday() < 5

    def previous_workday(date):
        for _ in range(30):
            working = workday(date)
            if working is None:
                return None
            if working:
                return date
            date -= dt.timedelta(days=1)
        return None

    known = str(day.year) in data['years']
    reasons = []
    if known:
        friday = day + dt.timedelta(days=4 - day.weekday())
        if previous_workday(friday) == day:
            reasons.append('本周周五或其之前最后一个工作日')
        for year in data['years'].values():
            for holiday in year['holidays']:
                previous = previous_workday(dt.date.fromisoformat(holiday['start']) - dt.timedelta(days=1))
                if previous == day:
                    reasons.append(holiday['name'] + '前最后一个工作日')
    elif day.weekday() == 4:
        reasons.append('日历缺失，临时按普通周五汇总')
    return {'date': day.isoformat(), 'calendar_verified': known, 'is_workday': workday(day),
            'weekly_due': bool(reasons), 'reasons': reasons,
            'refresh_next_year': day.month >= 11 and str(day.year + 1) not in data['years']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calendar', required=True)
    parser.add_argument('--date', required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(json.loads(Path(args.calendar).read_text()), dt.date.fromisoformat(args.date)), ensure_ascii=False))


if __name__ == '__main__':
    main()
