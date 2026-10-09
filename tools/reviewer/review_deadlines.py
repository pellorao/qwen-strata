"""Benchmark deadlines; messages and interruption use unchanged ARW APIs."""
import json
from datetime import datetime, timezone
from pathlib import Path
import time

LIMITS = {'initial': (3300, 3600), 'revision': (600, 900)}
REMINDER = ('请立即整理已经取得的审查结果，保存完整的原版Reviewer报告并返回。'
            '必须在剩余时间内结束，最多5分钟；到硬截止时仍在运行将被强制中断。'
            '保留已有发现、结论和证据，不改变报告格式，不声称未完成的工作已完成。')


def save(path, value):
    stage = path.with_suffix('.json.stage')
    stage.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    stage.replace(path)


class ReviewDeadline:
    def __init__(self, folder, accepted, started_at, phase='initial', clock=time.time,
                 start_source='harness task submission', alive_elapsed=None, work_elapsed=None):
        if phase not in LIMITS:
            raise ValueError('Unknown review phase')
        self.clock = clock
        if alive_elapsed is not None and work_elapsed is not None:
            raise ValueError('Provide only one work-time counter')
        self.alive_elapsed = work_elapsed if work_elapsed is not None else alive_elapsed
        self.path = Path(folder) / ('deadline-' + str(accepted['messageId']) + '.json')
        if self.path.exists():
            self.value = json.loads(self.path.read_text())
            if self.value['runId'] != accepted['runId'] or self.value['phase'] != phase:
                raise ValueError('Deadline identity changed')
        else:
            warning, hard = LIMITS[phase]
            self.value = {'runId': accepted['runId'], 'messageId': accepted['messageId'],
                'phase': phase, 'started_at': started_at, 'start_source': start_source,
                'reminder_at': started_at + warning, 'hard_deadline_at': started_at + hard,
                'reminder': None, 'interrupt': None,
                'time_basis': 'review-work' if self.alive_elapsed is not None else 'continuous loaded review',
                'reminder_after_seconds': warning, 'interrupt_after_seconds': hard}
            save(self.path, self.value)

    def advance(self, machine, observation):
        value = self.value
        if observation.get('runId') != value['runId']:
            raise ValueError('Deadline observation belongs to another run')
        # A deadline cannot restart a completed task or target another turn.
        snapshot = observation.get('snapshot') or {}
        root = next((m for m in snapshot.get('members', [])
                     if m.get('threadId') == observation.get('threadId')), None)
        if (observation.get('completion') or not root or root.get('state') != 'active'
                or not root.get('turnId') or snapshot.get('factsComplete') is not True):
            return
        now = self.clock()
        elapsed = self.alive_elapsed() if self.alive_elapsed is not None else now-value['started_at']
        warning, hard = LIMITS[value['phase']]
        if elapsed >= hard:
            operation, field, payload = 'interrupt_agent', 'interrupt', {}
        elif elapsed >= warning:
            remaining=max(0, int(hard-elapsed))
            if self.alive_elapsed is not None:
                message=REMINDER+f' 按审核工作时间累计，当前剩余{remaining}秒；停机和休眠期间暂停计时。'
            else:
                until = datetime.fromtimestamp(value['hard_deadline_at'], timezone.utc).isoformat()
                message = REMINDER + f' 硬截止为{until}，当前剩余{remaining}秒。'
            operation, field, payload = 'send_message', 'reminder', {'message': message}
        else:
            return
        if value[field] is not None:
            return
        payload.update(runId=value['runId'], turnId=root['turnId'])
        # Persist intent before sending: a transport failure is unknown, not
        # authorization to resend a potentially delivered message.
        value[field] = {'attempted_at': now, 'operation': operation,
                        'turnId': root['turnId'], 'status': 'unknown'}
        if field == 'reminder':
            value[field]['message'] = payload['message']
        save(self.path, value)
        try:
            receipt = machine.call(operation, payload)
            value[field]['receipt'] = receipt
            if not isinstance(receipt, dict) or receipt.get('runId') != value['runId']:
                raise RuntimeError('Deadline operation receipt identity is invalid')
            if (field == 'reminder' and (receipt.get('deliveryStatus') != 'accepted'
                    or not isinstance(receipt.get('messageId'), str))):
                raise RuntimeError('Deadline reminder was not acknowledged as accepted')
            if field == 'interrupt' and receipt.get('accepted') is not True:
                raise RuntimeError('Deadline interruption was not acknowledged as accepted')
            value[field]['status'] = 'accepted'
        except Exception as error:
            value[field]['error'] = str(error)
            save(self.path, value)
            raise
        save(self.path, value)

    def facts(self):
        value = self.value
        return {'phase': value['phase'], 'started_at': value['started_at'],
                'hard_deadline_at': value['hard_deadline_at'],
                'reminder': value['reminder'], 'interrupt': value['interrupt'],
                'time_basis': self.value.get('time_basis','legacy wall clock'),
                'record': str(self.path)}
