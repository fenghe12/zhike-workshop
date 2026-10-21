"""Preserve rejection feedback across retries without reusing rejected output."""
import json
from pathlib import Path


def reviewed_generation_requirements(directory, requirements):
    directory = Path(directory)
    review_path = directory / 'source-content-review.json'
    record_path = directory / 'generation-retry.json'
    previous = json.loads(record_path.read_text()) if record_path.is_file() else {}
    if not review_path.is_file():
        return requirements
    review = json.loads(review_path.read_text())
    if review.get('passed') is not False:
        return previous.get('requirements', requirements) if previous.get('baseRequirements') == requirements else requirements
    stamp = review_path.stat().st_mtime_ns
    if previous.get('reviewMtimeNs') == stamp and previous.get('baseRequirements') == requirements:
        return previous['requirements']
    rejected = [
        {'requirement': check['requirement'], 'reason': check.get('reason', ''),
         'rejectedText': [source.get('quote', '') for source in check.get('sources', [])]}
        for check in review.get('checks', []) if check.get('met') is False
    ]
    if not rejected:
        raise ValueError('生成复核失败，但未提供可用于重新生成的具体原因')
    revision = int(previous.get('revision', 0)) + 1
    updated = requirements + '\n重新生成修订序号：' + str(revision) + '\n以下是前次课件未通过的检查记录，请修正，禁止照抄被拒绝内容：\n' + json.dumps(rejected, ensure_ascii=False)
    pending = record_path.with_suffix('.pending.json')
    pending.write_text(json.dumps({'reviewMtimeNs': stamp, 'baseRequirements': requirements,
                                  'revision': revision, 'requirements': updated}, ensure_ascii=False))
    pending.replace(record_path)
    return updated
