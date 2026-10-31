"""Company-neutral immutable evidence and saved-run verification."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from company_initiation.shared_runtime import digest

def freeze_model_sources(data, archive, source_folder, *, previous=None, outputs=None):
    """Freeze originals, retaining verified historical files removed from the live archive.

    A changed live original is never replaced by an old copy. Missing originals
    may use an identical source from a verified parent; this is evidence reuse,
    not a company-specific input migration.
    """
    from .historic_construction.evidence import _local_file
    frozen=[];reused=[]
    prior_sources={s['id']:s for s in (previous or {}).get('sources',[])}
    descriptors=data['sources'].values() if isinstance(data['sources'],dict) else data['sources']
    for source in descriptors:
        try:
            raw=_local_file(archive,source['local_path']).read_bytes()
        except FileNotFoundError:
            prior=prior_sources.get(source['id'])
            if not previous or not previous.get('_reuse_verified') or not outputs or not prior or prior.get('sha256')!=source.get('sha256'):
                raise ValueError('Original is absent and no identical verified parent source is available: '+source['local_path'])
            prior_path=Path(prior['path']).resolve()
            raw=_local_file(Path(outputs).resolve(),str(prior_path.relative_to(Path(outputs).resolve()))).read_bytes()
            reused.append(dict(source_id=source['id'],local_path=source['local_path'],
                parent_path=str(prior_path),sha256=source['sha256'],reason='Original absent from current archive; verified frozen original retained'))
        if hashlib.sha256(raw).hexdigest()!=source['sha256']:
            raise ValueError('Source changed before freezing: '+source['local_path'])
        target=source_folder/(source['id']+Path(source['local_path']).suffix)
        target.write_bytes(raw)
        frozen.append(dict(source,path=str(target)))
    return frozen,reused


def verified_integrated_record(run, outputs):
    """Verify saved work before reuse; this never erases or settles ledger costs.

    Legacy incompatible settings do not make charges disappear. Call this after
    importing their accounting, and use only its returned detached record for
    response/artifact reuse. Parsing originals is not repeated here.
    """
    run,outputs=Path(run).resolve(),Path(outputs).resolve()
    if run.parent!=outputs or not run.is_dir():
        raise ValueError('Saved construction must be a direct run inside project outputs')
    record=json.loads((run/'record.json').read_text(encoding='utf-8'))
    record.pop('_reuse_verified',None)
    if Path(record.get('directory','')).resolve()!=run:
        raise ValueError('Saved construction directory identity disagrees with its record')
    calls=record.get('calls')
    if not isinstance(calls,list):
        raise ValueError('Saved construction has no valid call journal')
    journal=run/'calls.jsonl'
    saved_calls=[json.loads(line) for line in journal.read_text(encoding='utf-8').split('\n') if line.strip()] if journal.exists() else []
    if saved_calls!=calls:
        raise ValueError('Saved calls.jsonl differs from record; response reuse is prohibited')
    seen=set()
    for entry in calls:
        call_id=entry.get('call_id')
        if not isinstance(call_id,str) or not call_id or call_id in seen:
            raise ValueError('Saved journal has missing or duplicate request identities')
        seen.add(call_id)
        request=entry.get('request')
        if not isinstance(request,dict) or digest(request)!=entry.get('signature'):
            raise ValueError('Saved request signature is invalid; response reuse is prohibited')
        if request.get('model')!=entry.get('model'):
            raise ValueError('Saved request model disagrees with its call identity')
    artifacts=record.get('artifacts',{})
    if not isinstance(artifacts,dict):
        raise ValueError('Saved construction artifact inventory is invalid')
    for name,expected in artifacts.items():
        path=(run/name).resolve()
        if not path.is_relative_to(run) or not path.is_file():
            raise ValueError('Saved artifact is missing or outside its run: '+str(name))
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Saved artifact content changed: '+str(name))
    from company_initiation.shared_runtime import verify_source_bytes
    verify_source_bytes(record.get('sources',[]),outputs)
    record['_reuse_verified']=True
    return copy.deepcopy(record)


def integrated_runtime_fingerprint():
    """Exact local code/parser identity for reuse, without reading credentials."""
    from importlib.metadata import version, PackageNotFoundError
    import platform
    from .shared_runtime import _current_code_identity
    code=_current_code_identity()
    parsers={}
    for name in ('openpyxl','pypdf','xlrd'):
        try:parsers[name]=version(name)
        except PackageNotFoundError:parsers[name]='not-installed'
    return dict(version=1,code=code,parsers=parsers,python=platform.python_version())



def code_snapshot():
    """Shared immutable source snapshot using the same keys as the fingerprint."""
    from .shared_runtime import code_source_paths
    return {name: path.read_text(encoding='utf-8') for name, path in code_source_paths().items()}


def register_stage_output(journal, stage, output):
    """Durably register an exported checkpoint without granting model acceptance."""
    directory = Path(journal.directory).resolve()
    for name in output['files']:
        path = (directory / name).resolve()
        if not path.is_relative_to(directory) or not path.is_file():
            raise ValueError('Stage output is missing or outside its run: ' + name)
        journal.state['artifacts'][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    journal.state.setdefault('stage_outputs', {})[stage] = copy.deepcopy(output)
    journal.save()
    if getattr(journal, 'progress', None):
        journal.progress(f"{stage.capitalize()} stage export: {output.get('status')}; workbook: {directory / output['workbook']}")
