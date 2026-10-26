"""Operate a configured cloud session with an idle deadline and a total budget.

Start/stop commands are JSON argument arrays supplied by the operator. Start must
return a JSON computeState with a native cloud deadline. No account keys go into
the web service. Run this on the operator's persistent workstation or controller.
"""
from pathlib import Path
import argparse, json, os, subprocess, time
from urllib import request


def main(config_path):
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text())
    root = Path(config['runtimeDirectory']).resolve()
    root.mkdir(parents=True, exist_ok=True)
    for name in ['tmp', 'cache', 'logs']:
        (root/name).mkdir(exist_ok=True)
    os.environ.update({key: str(root/'tmp') for key in ['TMPDIR', 'TEMP', 'TMP']})
    os.environ['XDG_CACHE_HOME'] = str(root/'cache')
    token = Path(config['controlTokenFile']).read_text().strip()
    ledger_path = root/'budget-ledger.json'
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {'spentEstimateCny': 0, 'active': None}
    ceiling = float(config['hourlyCeilingCny'])
    budget = float(config['totalBudgetCny'])
    maximum = min(7200, int(config.get('maximumSessionSeconds', 3600)))
    if not 0 < budget <= 50 or not 0 < ceiling or maximum < 600:
        raise ValueError('Explicit budget and runtime limits are required')

    def save():
        ledger_path.write_text(json.dumps(ledger, indent=2))
        ledger_path.chmod(0o600)

    def api(payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {'Content-Type': 'application/json', 'X-Smartcourse-Control': token}
        req = request.Request(config['apiBase'].rstrip('/')+'/v1/compute/control', data=body, headers=headers)
        with request.urlopen(req, timeout=20) as response:
            return json.load(response)

    def stop():
        if not ledger.get('active'):
            return
        subprocess.run(config['stopCommand'], check=True, timeout=120)
        active = ledger['active']
        ledger['spentEstimateCny'] += (time.time()-active['startedEpoch'])/3600*ceiling
        ledger['active'] = None
        save()
        api({'computeState': {**active['computeState'], 'status': 'STOPPED', 'endpoints': []}})

    # Adoption is explicit and only uses an operator-provided owned lease.
    if not config.get('adoptActiveSession', False):
        stop()
    last_active = time.time()
    try:
        while True:
            snapshot = api()
            pending = [item for item in snapshot['requests'] if item['status'] == 'pending']
            if ledger['active']:
                active = ledger['active']
                elapsed = time.time()-active['startedEpoch']
                if snapshot['activeTaskCount']:
                    last_active = time.time()
                if time.time() >= active['deadlineEpoch']-90 or time.time()-last_active >= int(config.get('idleSeconds', 300)):
                    stop()
                elif pending:
                    api({'requestIds': [item['id'] for item in pending]})
            elif pending:
                reserve = maximum/3600*ceiling
                eligible = [item for item in pending if float(item['budgetCny']) >= reserve]
                insufficient = [item['id'] for item in pending if float(item['budgetCny']) < reserve]
                if insufficient:
                    api({'requestIds': insufficient, 'requestStatus': 'budget_too_low'})
                if not eligible:
                    time.sleep(20)
                    continue
                if ledger['spentEstimateCny']+reserve > budget:
                    api({'requestIds': [item['id'] for item in pending], 'requestStatus': 'budget_exhausted'})
                else:
                    started = time.time()
                    ledger['active'] = {'startedEpoch': started, 'deadlineEpoch': started+maximum,
                        'computeState': {'smartcourseOwner': config['computeOwner'], 'status': 'STARTING',
                                         'smartcourseDeadline': started+maximum, 'endpoints': []}}
                    save()
                    result = subprocess.run(config['startCommand'], capture_output=True, text=True, check=True,
                                            timeout=min(maximum-180, 1800))
                    state = json.loads(result.stdout)['computeState']
                    if not started < float(state['smartcourseDeadline']) <= started+maximum:
                        subprocess.run(config['stopCommand'], check=True, timeout=120)
                        raise ValueError('Cloud start did not return a bounded native session')
                    ledger['active'] = {'startedEpoch': started, 'deadlineEpoch': float(state['smartcourseDeadline']), 'computeState': state}
                    save()
                    api({'computeState': state, 'requestIds': [item['id'] for item in eligible]})
                    last_active = time.time()
            time.sleep(20)
    finally:
        stop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('config', help='Private persistent JSON configuration')
    main(parser.parse_args().config)
