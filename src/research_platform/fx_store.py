"""Shared, append-only FX evidence and immutable calculation snapshots (SQLite).

Provider-native quotes, workbook projections and derived period summaries have
different roles. Imports never overwrite earlier observations. Conflicting
revisions are quarantined; a snapshot pins exact evidence and selection policy.
No company model or provider/AI client is imported here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class FXStore:
    def __init__(self,path):
        self.path=Path(path).resolve()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.path,timeout=30)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS imports(id TEXT PRIMARY KEY, imported_at TEXT NOT NULL, metadata TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS quotes(id TEXT PRIMARY KEY, provider TEXT NOT NULL,
            base TEXT NOT NULL, quote TEXT NOT NULL, day TEXT NOT NULL, definition TEXT NOT NULL,
            status TEXT NOT NULL, quality TEXT NOT NULL, value REAL NOT NULL, payload TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS quote_lookup ON quotes(base,quote,day,provider,definition);
          CREATE TABLE IF NOT EXISTS quote_imports(quote_id TEXT REFERENCES quotes(id), import_id TEXT REFERENCES imports(id),
            PRIMARY KEY(quote_id,import_id));
          CREATE TABLE IF NOT EXISTS period_snapshots(id TEXT PRIMARY KEY, import_id TEXT REFERENCES imports(id), payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS policies(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS update_runs(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL);
        ''')

    def __enter__(self):return self

    def __exit__(self,*args):self.db.close()

    def import_quotes(self,quotes,metadata,periods=()):
        """Atomically preserve evidence; exact repeat imports are idempotent."""
        import_id=fingerprint(metadata)
        added=duplicates=quarantined=0
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO imports VALUES(?,?,?)',(import_id,utc_now(),canonical(metadata)))
            for original in quotes:
                q=dict(original)
                required=('provider','base','quote','day','definition','value','status','source_date','timezone')
                if any(q.get(k) is None for k in required):raise ValueError('FX observation missing required metadata')
                from .fx import _number, _date
                if _number(q['value']) is None:raise ValueError('Nonpositive/nonfinite FX quote')
                _date(q['day']);_date(q['source_date'])
                if q['status'] not in ('actual','projected','carried'):raise ValueError('Invalid FX evidence status')
                if q['status']=='actual' and q['source_date']!=q['day']:
                    raise ValueError('A carried quote cannot be an actual observation for another day')
                if q['definition']=='bid_ask_midpoint':
                    from .ibkr import validate_spot
                    stamped=datetime.fromisoformat(q['timestamp'].replace('Z','+00:00'))
                    validated=validate_spot(q,stamped)
                    if abs(q['value']/validated['value']-1)>1e-12:raise ValueError('Stored midpoint differs from bid/ask')
                # Provider revisions are retained but never replace an accepted fact implicitly.
                old=self.db.execute('SELECT value FROM quotes WHERE provider=? AND base=? AND quote=? AND day=? AND definition=? AND status=? AND quality=?',
                    (q['provider'],q['base'],q['quote'],q['day'],q['definition'],q['status'],'accepted')).fetchall()
                q.setdefault('quality','accepted')
                if q['definition']!='bid_ask_midpoint' and any(abs(r['value']/q['value']-1)>1e-12 for r in old):q['quality']='quarantined_revision'
                volatile=('id','retrieved_at','imported_at','quality','provenance','file_version','selection_priority','age_seconds','market_closed',
                    'transition_status','extension_approved')
                identity={k:v for k,v in q.items() if k not in volatile}
                qid=fingerprint(identity);q['id']=qid
                if q['definition']=='bid_ask_midpoint':
                    # Retain identities created before age metadata was excluded.
                    for saved in self.db.execute('SELECT id,payload FROM quotes WHERE provider=? AND base=? AND quote=? AND day=? AND definition=?',
                            (q['provider'],q['base'],q['quote'],q['day'],q['definition'])):
                        previous=json.loads(saved['payload'])
                        if {k:v for k,v in previous.items() if k not in volatile}==identity:
                            qid=saved['id'];q['id']=qid;break
                cur=self.db.execute('INSERT OR IGNORE INTO quotes VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (qid,q['provider'],q['base'],q['quote'],q['day'],q['definition'],q['status'],q['quality'],q['value'],canonical(q)))
                added+=cur.rowcount;duplicates+=1-cur.rowcount
                quarantined+=cur.rowcount if q['quality']!='accepted' else 0
                self.db.execute('INSERT OR IGNORE INTO quote_imports VALUES(?,?)',(qid,import_id))
            for p in periods:
                self.db.execute('INSERT OR IGNORE INTO period_snapshots VALUES(?,?,?)',(fingerprint(dict(p,import_id=import_id)),import_id,canonical(p)))
        return dict(import_id=import_id,added=added,duplicates=duplicates,quarantined=quarantined,ai_calls=0)

    def import_workbook(self,path,adapter=None):
        from .fx import load_fx_source
        source=load_fx_source(path,adapter=adapter)
        metadata=dict(source['source'],kind='workbook',adapter=adapter or {},metadata=source['metadata'])
        quotes=[];projection_dates={d for days in source['metadata']['projected_publication_dates'].values() for d in days}
        selected={(code,s['sheet']) for code,s in source['daily_series'].items()}
        for series in source.get('all_daily_series',[]):
            code=series['currency']
            for p in series['points']:
                if p['value'] is None:continue
                projected=p['date'] in projection_dates or bool(source['metadata'].get('spot_reference_date') and p['date']>source['metadata']['spot_reference_date'])
                source_date=p['source_date'] or p['date']
                provenance=p['provenance']
                derived=bool(provenance.get('formula'))
                quotes.append(dict(provider=str(p['provider']),base=series['base_currency'],quote=code,day=p['date'],
                    value=p['value'],source_date=source_date,status='projected' if projected else 'carried' if source_date!=p['date'] else 'actual',
                    definition='workbook_normalized_reference' if derived else 'reference_fixing',
                    timezone='source_date_only; intraday time undisclosed',observation_time=None,
                    native=not derived,selection_priority=0 if (code,series['sheet']) in selected else 10,
                    provenance=provenance,file_version=source['source']['sha256'],retrieved_at=None,
                    lineage=dict(sheet=series['sheet'],header=series['header_cell'],formula=provenance.get('formula'))))
        return self.import_quotes(quotes,metadata,source['observations'])

    def quotes(self,*,accepted=True):
        query='SELECT payload FROM quotes'+(" WHERE quality='accepted'" if accepted else '')+' ORDER BY day,provider,base,quote,id'
        return [json.loads(r[0]) for r in self.db.execute(query)]

    def import_ecb(self,payload,*,url='https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml'):
        """ECB's native EUR reference fixings; keep overlap and revisions visible."""
        import xml.etree.ElementTree as ET
        from .ibkr import overlap_check
        root=ET.fromstring(payload);quotes=[];version=hashlib.sha256(payload).hexdigest()
        for node in root.iter():
            if 'time' not in node.attrib:continue
            day=node.attrib['time']
            for child in node:
                if 'currency' not in child.attrib or 'rate' not in child.attrib:continue
                quotes.append(dict(provider='ECB',base='EUR',quote=child.attrib['currency'],day=day,source_date=day,
                    value=float(child.attrib['rate']),status='actual',definition='reference_fixing',timezone='Europe/Frankfurt',
                    observation_time='ECB reference rate publication; not a market close',native=True,selection_priority=-1,
                    retrieved_at=utc_now(),file_version=version,provenance=dict(url=url,sha256=version)))
        existing=self.quotes();audits=[]
        # Preserve the old workbook observations in overlap; extend at the existing
        # boundary. A newer downloaded revision does not rewrite imported history.
        selected=[]
        for currency in sorted({q['quote'] for q in quotes}):
            subset=[q for q in quotes if q['quote']==currency]
            audit=overlap_check(existing,subset,'EUR',currency);audits.append(audit)
            last=max((q['day'] for q in existing if q['base']=='EUR' and q['quote']==currency and q['status']=='actual'),default='')
            for q in subset:
                q['selection_priority']=20 if q['day']<=last else -1
                q['transition_status']=audit['status'] if last else 'initial_series'
                q['extension_approved']=audit['status']=='passed' or not last
                if audit['status']=='quarantined':q['quality']='quarantined_transition'
                selected.append(q)
        result=self.import_quotes(selected,dict(kind='ecb_reference_xml',url=url,sha256=version))
        result['overlap']=audits
        return result

    def save_policy(self,policy):
        """Explicit cutovers name pairs/providers/dates and preserve overlap evidence."""
        for transition in policy.get('cutovers',[]):
            if not all(transition.get(k) for k in ('base','quote','provider','from','overlap_evidence','reason')):
                raise ValueError('Cutover requires dated pair, provider, overlap evidence and reason')
            if transition.get('quarantined') or transition['overlap_evidence'].get('status')!='passed':raise ValueError('Unresolved provider transition cannot be promoted')
        key=fingerprint(policy)
        with self.db:self.db.execute('INSERT OR IGNORE INTO policies VALUES(?,?,?)',(key,utc_now(),canonical(policy)))
        return key

    def snapshot(self,as_of,policy=None):
        from .fx import prepare_snapshot
        policy=dict(policy or {})
        if len(as_of)==10:as_of+='T23:59:59+00:00'
        dt=datetime.fromisoformat(as_of.replace('Z','+00:00'))
        if dt.tzinfo is None:raise ValueError('FX snapshot as-of requires a timezone')
        policy_id=self.save_policy(policy)
        imports=[dict(r) for r in self.db.execute('SELECT * FROM imports ORDER BY id')]
        eligible=[q for q in self.quotes() if q['day']<=dt.date().isoformat() and q['status']!='projected'
                  and (not q.get('timestamp') or datetime.fromisoformat(q['timestamp'].replace('Z','+00:00'))<=dt)]
        snapshot=prepare_snapshot(eligible,as_of,policy)
        snapshot.update(policy_id=policy_id,import_ids=[r['id'] for r in imports])
        snapshot_id=fingerprint(snapshot)
        snapshot['source']=dict(snapshot_id=snapshot_id,sha256=snapshot_id,filename='shared FX database snapshot',path=str(self.path),format='sqlite_snapshot_v1')
        with self.db:self.db.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?)',(snapshot_id,utc_now(),canonical(snapshot)))
        return snapshot

    def get_snapshot(self,snapshot_id):
        row=self.db.execute('SELECT payload FROM snapshots WHERE id=?',(snapshot_id,)).fetchone()
        if row is None:raise ValueError('Unknown FX snapshot '+snapshot_id)
        return json.loads(row[0])

    def record_update(self,result):
        key=fingerprint(result)
        with self.db:self.db.execute('INSERT OR IGNORE INTO update_runs VALUES(?,?,?)',(key,utc_now(),canonical(result)))
        return key

    def status(self):
        counts={table:self.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('imports','quotes','period_snapshots','snapshots')}
        series=[dict(r) for r in self.db.execute("SELECT provider,base,quote,definition,status,quality,MIN(day) AS first,MAX(day) AS last,COUNT(*) AS observations FROM quotes GROUP BY provider,base,quote,definition,status,quality")]
        latest=self.db.execute('SELECT payload FROM update_runs ORDER BY created_at DESC LIMIT 1').fetchone()
        latest=json.loads(latest[0]) if latest else {}
        daily=max((s['last'] for s in series if s['status']=='actual' and s['quality']=='accepted' and s['definition']!='bid_ask_midpoint'),default=None)
        spot=self.db.execute("SELECT MAX(json_extract(payload,'$.timestamp')) FROM quotes WHERE definition='bid_ask_midpoint' AND quality='accepted'").fetchone()[0]
        return dict(database=str(self.path),counts=counts,series=series,ai_calls=0,as_of=utc_now(),
            latest_actual_daily_date=daily,latest_spot_observed_at=spot,last_update_status=latest.get('status'),
            freshness_note='Provider/pair coverage is in series; global latest dates do not certify every required currency. Model snapshots enforce per-path freshness.')

    def latest_policy(self):
        row=self.db.execute('SELECT payload FROM policies ORDER BY created_at DESC LIMIT 1').fetchone()
        return json.loads(row[0]) if row else dict(calendar=dict(name='TARGET'),fixing_max_age_business_days=1,
            max_carry_business_days=0,provider_priority=['IBKR','ECB','ECB Daily'],cutovers=[])


def fx_command(root,args):
    """Shared-factor CLI operations. Never invokes company research or an LLM."""
    import tomllib
    from uuid import uuid4
    defaults=tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8')).get('tool',{}).get('research-platform',{})
    database=Path(args.database or defaults.get('fx-database','local_store/FX/fx.sqlite'))
    if not database.is_absolute():database=root/database
    directory=root/'outputs'/('fx_'+args.command.removeprefix('fx-')+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid4().hex[:8])
    directory.mkdir(parents=True)
    with FXStore(database) as store:
        if args.command=='fx-import':
            path=Path(args.workbook or defaults.get('fx-source',''))
            if not path.is_absolute():path=root/path
            result=store.import_workbook(path)
        elif args.command=='fx-status':result=store.status()
        elif args.command=='fx-update-ecb':
            import urllib.request
            import ssl
            import subprocess
            import shutil
            url='https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml'
            target=directory/'ecb_reference_original.xml'
            try:target.write_bytes(urllib.request.urlopen(url,timeout=30).read())
            except urllib.error.URLError as exc:
                # Windows curl uses the OS certificate store. Never disable TLS
                # validation or retry against an unauthenticated HTTP endpoint.
                if not isinstance(exc.reason,ssl.SSLCertVerificationError) or not shutil.which('curl.exe'):raise
                subprocess.run(['curl.exe','--fail','--silent','--show-error','--max-time','30',url,'-o',str(target)],check=True)
            result=store.import_ecb(target.read_bytes(),url=url)
            result['original']=str(target)
        else:
            from .ibkr import TWSClient,update_fx,BrokerError
            settings=defaults.get('ibkr',{});client=None
            try:
                client=TWSClient(host=args.host or settings.get('host','127.0.0.1'),port=args.port or settings.get('port',7497),
                    client_id=args.client_id if args.client_id is not None else settings.get('client-id',71),
                    session_timezone=args.session_timezone or settings.get('session-timezone','UTC'))
                print('Read-only API handshake: '+canonical(client.handshake),flush=True)
                pairs=args.pairs or settings.get('pairs')
                if not pairs:raise ValueError('Configure shared IBKR pairs or pass --pairs')
                result=update_fx(store,client,pairs,overlap_days=args.overlap_days or settings.get('overlap-days',7),
                    max_recent_days=args.max_recent_days or settings.get('max-recent-days',90),
                    diagnostic=args.diagnostic,progress=lambda message:print(message,flush=True))
                result['handshake']=client.handshake
                if not args.diagnostic:
                    policy=store.latest_policy()
                    for transition in result['cutovers']:
                        old=next((t for t in policy['cutovers'] if (t['base'],t['quote'],t['provider'])==(transition['base'],transition['quote'],transition['provider'])),None)
                        if old is None:policy['cutovers'].append(transition)
                    result['policy_id']=store.save_policy(policy)
            except BrokerError as exc:result=dict(status='unavailable',exit_code=2,error=str(exc),ai_calls=0)
            finally:
                if client:client.close()
        (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(canonical({k:v for k,v in result.items() if k not in ('series','pairs','overlap','cutovers')}),flush=True)
        print('Saved FX audit: '+str(directory/'result.json'),flush=True)
        return result.get('exit_code',0)
