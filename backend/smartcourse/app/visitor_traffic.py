"""First-party visitor IP and approximate region statistics using an offline database."""
import ipaddress
import os
from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Shanghai')
NETWORK_LABELS = {'public':'公网', 'private':'校园网或内网', 'loopback':'服务器本机',
                  'link_local':'本地链路', 'reserved':'保留地址', 'unknown':'未记录'}


def client_ip(peer, headers):
    """Only the local reverse proxy may provide a single forwarded address."""
    try:
        address = ipaddress.ip_address(peer)
        if address.is_loopback:
            try:
                address = ipaddress.ip_address(headers.get('X-Real-IP', peer))
            except ValueError:
                pass
        return str(address.ipv4_mapped or address) if isinstance(address, ipaddress.IPv6Address) else str(address)
    except ValueError:
        return ''


class IpLocator:
    def __init__(self, root):
        self.root = Path(os.environ.get('SMARTCOURSE_GEOIP_ROOT', Path(root)/'geoip'))
        self.searchers = {}
        try:
            import ip2region.util as util
            import ip2region.searcher as xdb
            for version, kind in [(4, util.IPv4), (6, util.IPv6)]:
                path = self.root/f'ip2region_v{version}.xdb'
                if path.is_file():
                    util.verify_from_file(str(path))
                    self.searchers[version] = xdb.new_with_buffer(kind, util.load_content_from_file(str(path)))
        except Exception:
            self.searchers = {}

    @lru_cache(maxsize=4096)
    def describe(self, value):
        result = {'ip':value, 'scope':'unknown', 'country':'', 'province':'', 'city':'', 'isp':'', 'countryCode':'', 'source':'unrecorded'}
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return result
        if address.is_loopback: scope = 'loopback'
        elif address.is_link_local: scope = 'link_local'
        elif address.is_global: scope = 'public'
        elif address.is_private: scope = 'private'
        else: scope = 'reserved'
        result.update(scope=scope, source='network_address')
        if scope != 'public': return result
        searcher = self.searchers.get(address.version)
        if not searcher: return result
        try:
            fields = searcher.search(str(address)).split('|')
            if len(fields) >= 5:
                result.update(zip(('country','province','city','isp','countryCode'), (v if v != '0' else '' for v in fields[:5])))
                result['source'] = 'ip2region_offline'
        except (ValueError, OSError):
            pass
        return result


def _distribution(counter):
    total = sum(counter.values())
    return [{'label':label, 'count':count, 'percent':round(count*100/total,1) if total else 0}
            for label,count in counter.most_common()]


def traffic_report(events, users):
    visits = [e for e in events if e['kind']=='page_view']
    known = [e for e in visits if e.get('network',{}).get('ip')]
    ips, daily = {}, defaultdict(lambda:{'views':0,'ips':set(),'users':set()})
    countries, provinces, cities, scopes = Counter(), Counter(), Counter(), Counter()
    for event in visits:
        network=event.get('network') or {}; ip=network.get('ip'); scope=network.get('scope','unknown')
        label=NETWORK_LABELS.get(scope,'未记录');scopes[label]+=1
        country=network.get('country') or (label if scope!='public' else '公网地域未识别')
        countries[country]+=1
        provinces[network.get('province') or country]+=1
        cities[network.get('city') or network.get('province') or country]+=1
        day=datetime.fromtimestamp(event['created'],TZ).strftime('%Y-%m-%d');daily[day]['views']+=1
        if ip: daily[day]['ips'].add(ip)
        if event['user_id']:daily[day]['users'].add(event['user_id'])
        if not ip:continue
        row=ips.setdefault(ip,{'ip':ip,'scope':scope,'networkLabel':label,'country':network.get('country'),'province':network.get('province'),'city':network.get('city'),'isp':network.get('isp'),'source':network.get('source'),'views':0,'users':set(),'firstSeen':event['created'],'lastSeen':event['created']})
        row['views']+=1;row['firstSeen']=min(row['firstSeen'],event['created']);row['lastSeen']=max(row['lastSeen'],event['created'])
        if event['user_id']:row['users'].add(event['user_id'])
    for row in ips.values():
        row['userCount']=len(row['users']);row['userNames']=[users.get(uid,{}).get('displayName','历史账号') for uid in sorted(row.pop('users'))]
        for key in ('firstSeen','lastSeen'):row[key]=datetime.fromtimestamp(row[key],TZ).isoformat()
    return {'summary':{'pageViews':len(visits),'uniqueIps':len(ips),'loggedInUsers':len({e['user_id'] for e in visits if e['user_id']}),'anonymousViews':sum(not e['user_id'] for e in visits),'missingIpViews':len(visits)-len(known)},
            'countries':_distribution(countries),'provinces':_distribution(provinces),'cities':_distribution(cities),'networks':_distribution(scopes),
            'ips':sorted(ips.values(),key=lambda row:row['lastSeen'],reverse=True),
            'daily':[{'date':day,'pageViews':row['views'],'uniqueIps':len(row['ips']),'loggedInUsers':len(row['users'])} for day,row in sorted(daily.items())],
            'notes':['地域来自访问 IP 的离线查询，表示网络出口的大致地域。','校园网、VPN、代理及共享出口可能对应同一个 IP，独立 IP 数不等于独立人数。','内网与服务器本机地址不推断实际地域；历史缺少 IP 的访问显示未记录。','匿名访问仅记录页面与网络信息，不读取设备位置。']}
