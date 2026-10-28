"""Set administrator access from the server's maintenance session."""
import argparse
import json
import os
from .config import Settings
from .store import JsonStore
from .task_model import utc_now


def main():
    parser=argparse.ArgumentParser(description='配置智课工坊管理员账号')
    parser.add_argument('--account',required=True)
    parser.add_argument('--remove',action='store_true')
    args=parser.parse_args();settings=Settings.from_env();store=JsonStore(settings.data_root/'state.json')
    if args.account not in store.snapshot().get('users',{}):raise SystemExit('此账号尚未注册')
    path=settings.data_root/'admin-access.json';data=json.loads(path.read_text()) if path.exists() else {'accounts':[]}
    accounts=set(data.get('accounts',[]))
    if args.remove:accounts.discard(args.account)
    else:accounts.add(args.account)
    data.update(accounts=sorted(accounts),updatedAt=utc_now());pending=path.with_suffix('.pending');pending.write_text(json.dumps(data,ensure_ascii=False,indent=2));pending.chmod(0o600);os.replace(pending,path)
    print('管理员访问配置已更新，无需重新启动服务。')


if __name__=='__main__':main()
