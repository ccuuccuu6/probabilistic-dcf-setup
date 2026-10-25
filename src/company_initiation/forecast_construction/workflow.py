"""Forecast-model refresh and export operations, consuming saved history."""
from datetime import date, datetime, timezone
import copy
import hashlib
import json
from pathlib import Path
import shutil
from uuid import uuid4

def model_financial_completeness(spec):
    """Keep material portfolio-accounting omissions separate from arithmetic.

    Passing calculations or Excel comparisons cannot complete an event's missing
    consideration, derecognition or retained-interest accounting. Other models
    remain provisional; absence of this particular gap is not economic validation.
    """
    return ('incomplete_scope_accounting' if any(event.get('material_unresolved')
        for event in spec.get('scope_event_audit',[])) else 'provisional')


def offline_export(root, run, *, fx_file=None, fx_database=None, snapshot_id=None, fx_as_of=None, inputs_file=None, recalculate=True, progress=None,
                   include_valuation=False,valuation_date=None,rebuild=False):
    """Re-export saved inputs, optionally refreshing only shared FX, with zero AI."""
    from ..shared_budget import BudgetLedger, ledger_path, company_key
    from ..shared_runtime import write_json, digest
    from .construction import recalculate_workbook
    from ..shared_artifacts import verified_integrated_record
    from company_initiation.forecast_construction.integrated import build_periodic_spec, periodic_sensitivities
    from ..historic_construction.initiation import _initiation_lock
    from company_initiation.forecast_construction.periods import calculate_periodic, validate_periodic
    from company_initiation.forecast_construction.model_excel import export_integrated, verify_excel_sensitivities
    from shared_FX.fx import load_fx_source
    root=Path(root).resolve();outputs=root/'outputs';prior=Path(run)
    if not prior.is_absolute():prior=outputs/prior
    previous=json.loads((prior/'record.json').read_text(encoding='utf-8'))
    previous=verified_integrated_record(prior,outputs)
    config=copy.deepcopy(previous['configuration']);company=config['company']
    with _initiation_lock(outputs,scope=company_key(company)):
        ledger=BudgetLedger(ledger_path(outputs,company),company,config['limits']['usd'])
        ledger.import_record(previous)
        before=ledger.summary()
        data=json.loads((prior/'company_model_inputs.json').read_text(encoding='utf-8'))
        original_data=copy.deepcopy(data)
        if inputs_file:
            revised=json.loads(Path(inputs_file).read_text(encoding='utf-8'))
            for key,value in data.items():
                if key not in ('model_configuration','sources') and revised.get(key)!=value:
                    raise ValueError('Offline exposure/policy refresh cannot revise company historical evidence: '+key)
            if any(revised.get('sources',{}).get(sid)!=source for sid,source in data['sources'].items()):
                raise ValueError('Offline configuration must preserve existing company source identities')
            data=revised
        oldspec=json.loads((prior/'model_specification.json').read_text(encoding='utf-8'))
        directory=outputs/('construct_refresh_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid4().hex[:8])
        directory.mkdir()
        # Verified immutable originals are shared across preserved continuations.
        # Only a changed shared-factor original needs a new frozen copy.
        frozen=copy.deepcopy(previous['sources'])
        for sid,source in data['sources'].items():
            if sid in original_data['sources']:continue
            from ..historic_construction.evidence import _local_file
            raw=_local_file(Path(config['sources']),source['local_path']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=source['sha256']:raise ValueError('Changed new configuration evidence '+sid)
            (directory/'sources').mkdir(exist_ok=True)
            target=directory/'sources'/(sid+Path(source['local_path']).suffix);target.write_bytes(raw)
            frozen.append(dict(source,path=str(target)))
        if data['model_configuration'].pop('refresh_vendor_bindings',False):
            from ..historic_construction.evidence import migrate_vendor_bindings
            migration=migrate_vendor_bindings(data,previous['sources'],frozen)
            write_json(directory/'vendor_binding_migration.json',migration)
            if progress:progress(f'Migrated {len(migration)} unchanged vendor bindings by exact label, unit, period and value; no AI calls.')
        fx=None
        if fx_database:
            from shared_FX.fx_store import FXStore
            if not Path(fx_database).is_file():raise ValueError('Shared FX database missing; run fx-import first')
            with FXStore(fx_database) as store:
                fx=store.get_snapshot(snapshot_id) if snapshot_id else store.snapshot(
                    fx_as_of or datetime.now(timezone.utc).isoformat(),store.latest_policy())
            data['model_configuration']['fx_as_of']=fx['as_of']
            write_json(directory/'fx_snapshot.json',fx)
            spec=build_periodic_spec(data,len(oldspec['forecast_years']),fx)
            config['input_hash']=digest(dict(data=data,fx=fx['source']))
            config['fx_database']=str(Path(fx_database).resolve());config['fx_snapshot_id']=fx['source']['snapshot_id']
        elif fx_file:
            fx=load_fx_source(Path(fx_file),adapter=data.get('model_configuration',{}).get('fx_adapter'))
            fx_hash=hashlib.sha256(Path(fx_file).read_bytes()).hexdigest()
            existing=next((s for s in frozen if s['id']=='shared_fx' and s['sha256']==fx_hash),None)
            if not existing:
                (directory/'sources').mkdir()
                target=directory/'sources'/('shared_fx'+Path(fx_file).suffix)
                shutil.copyfile(fx_file,target)
                frozen=[s for s in frozen if s['id']!='shared_fx']+[dict(id='shared_fx',path=str(target),sha256=fx_hash,category='shared_factor',local_path=str(fx_file))]
            spec=build_periodic_spec(data,len(oldspec['forecast_years']),fx)
            config['input_hash']=digest(dict(data=data,fx=dict(path=str(Path(fx_file).resolve()),sha256=hashlib.sha256(Path(fx_file).read_bytes()).hexdigest())))
            config['fx_source']=str(Path(fx_file).resolve())
        elif inputs_file or rebuild:
            previous_fx=prior/'fx_snapshot.json'
            fx=json.loads(previous_fx.read_text(encoding='utf-8')) if previous_fx.is_file() else None
            spec=build_periodic_spec(data,len(oldspec['forecast_years']),fx)
        else:
            spec=copy.deepcopy(oldspec)
        # An ordinary export or company-policy refresh retains the same pinned
        # market state. A supplied replacement database/workbook owns its own
        # factor provenance and must not inherit an obsolete snapshot.
        if not fx_database and not fx_file and (prior/'fx_snapshot.json').is_file():
            shutil.copyfile(prior/'fx_snapshot.json',directory/'fx_snapshot.json')
        if oldspec.get('assumption_payload'):
            from company_initiation.forecast_construction.periods import apply_assumption_payload
            spec=apply_assumption_payload(spec,oldspec['assumption_payload'],allow_model_refresh=True)
        from company_initiation.forecast_construction.periods import assumption_contract
        spec['input_contract']=assumption_contract(spec)
        spec['financial_completeness']=model_financial_completeness(spec)
        spec['sources']=frozen
        values=calculate_periodic(spec)
        refresh_audit=None
        if fx:
            old_values=json.loads((prior/'forecast.json').read_text(encoding='utf-8'))
            changed=[]
            for row in spec['rows']:
                for pid,value in values[row['id']].items():
                    old=old_values.get(row['id'],{}).get(pid)
                    if old!=value:changed.append(dict(row_id=row['id'],period_id=pid,before=old,after=value,section=row['section']))
            refresh_audit=dict(previous_source=oldspec.get('fx_source'),new_source=fx['source'],
                previous_vintage=oldspec.get('fx_metadata',{}).get('daily_end'),new_vintage=fx['metadata'].get('daily_end'),
                changed_cells=changed,ai_calls=0,company_observations_unchanged=data.get('observations')==original_data.get('observations'),
                company_historical_values_unchanged=[(o['id'],o['value']) for o in data.get('observations',[])]==[(o['id'],o['value']) for o in original_data.get('observations',[])],
                economic_interface=spec.get('fx_interfaces',{}))
        saved_checks=json.loads((prior/'validation.json').read_text(encoding='utf-8'))['checks']
        # Retain all frozen source/annual-contract reviews. Current period, FX
        # and financial-contract checks are regenerated, including warnings;
        # retaining them would accumulate stale duplicates on each refresh.
        recomputed={'period_derivation','period_identity','period_sensitivity','period_graph','period_values','period_formula',
            'fx_exposure','transaction_fx','fx_contract',
            'financial_contracts','financial_contract','scope_bridge','cost_pool','fx_accounting','exposure_quality','driver_contract','valuation'}
        checks=[dict(c,verification_scope='Preserved prior source/annual review; see parent run') for c in saved_checks if c.get('area') not in recomputed]
        checks+=validate_periodic(spec,values)
        cases,behavior=periodic_sensitivities(spec,values);checks+=behavior;spec['sensitivity_cases']=cases
        valuation=None
        if include_valuation or (prior/'valuation_inputs.json').is_file():
            previous_valuation=json.loads((prior/'valuation_inputs.json').read_text(encoding='utf-8')) if (prior/'valuation_inputs.json').is_file() else None
            from ..dcf_construction.workflow import valuation_snapshot
            valuation=valuation_snapshot(spec,values,data,valuation_date=valuation_date,previous_inputs=previous_valuation)
            checks+=valuation['checks']
            for name,content in valuation['artifacts'].items():write_json(directory/name,content)
            config['valuation']=dict(enabled=True,date=valuation['result']['valuation_date'])
        inspection=export_integrated(directory/'model.xlsx',spec,values,checks,valuation=valuation['result'] if valuation else None)
        if recalculate:
            inspection['recalculation']=recalculate_workbook(directory/'model.xlsx',inspection)
            if inspection['recalculation'].get('status')=='passed':
                inspection['sensitivities']=verify_excel_sensitivities(directory/'model.xlsx',spec,inspection,output_directory=directory)
        from company_initiation.forecast_construction.model_excel import validate_workbook_layout
        inspection['layout']=validate_workbook_layout(directory/'model.xlsx',inspection)
        status='complete_provisional' if not any(c['status'] in ('FAIL','MISSING') for c in checks) and inspection.get('recalculation',{}).get('status')=='passed' and inspection.get('sensitivities',{}).get('status')=='passed' and inspection['layout'].get('status')=='passed' else 'incomplete_model'
        record=copy.deepcopy(previous)
        record.update(directory=str(directory),parent_run=str(prior),configuration=config,sources=frozen,status=status,
            financial_completeness=spec['financial_completeness'],artifacts={},pending_call=None,issues=[],budget=ledger.summary())
        record.setdefault('summary',{}).update(rows=len(spec['rows']),segments=len(data.get('segments',[])),
            assumptions=sum(r.get('kind')=='assumption' for r in spec['rows']),
            historical_years=list(spec.get('historical_years',data.get('history_years',[]))),
            forecast_years=list(spec.get('forecast_years',[])),
            checks={state:sum(c.get('status')==state for c in checks) for state in ('PASS','FAIL','MISSING','WARNING')})
        # A new market snapshot is not itself a changed company modelling policy.
        # Keep that distinction visible even when the CLI operation remains an
        # FX refresh for compatibility with existing callers.
        market_operation_keys={'fx_as_of','refresh_vendor_bindings'}
        prior_model_config={k:v for k,v in original_data.get('model_configuration',{}).items() if k not in market_operation_keys}
        current_model_config={k:v for k,v in data.get('model_configuration',{}).items() if k not in market_operation_keys}
        changed_model_fields=sorted(k for k in prior_model_config.keys()|current_model_config.keys()
            if k not in prior_model_config or k not in current_model_config or prior_model_config[k]!=current_model_config[k])
        policy_changed=bool(changed_model_fields) or oldspec.get('policies')!=spec.get('policies')
        record['operation']=dict(kind='fx_refresh' if fx else 'reexport',ai_calls=0,
            model_configuration_changed=bool(changed_model_fields),changed_model_configuration_fields=changed_model_fields,
            calculation_policy_changed=policy_changed or rebuild,recompiled_shared_engine=bool(rebuild),
            calculation_policy='Deterministic calculation policy changed; no new AI review or acceptance.' if policy_changed else
                'Company calculation policy retained; deterministic snapshot/export operation with no AI calls.',
            budget_before=before,budget_after=ledger.summary(),source_reviews='Frozen previous source reviews; new financial contracts, FX and frequency logic are deterministically tested, with no renewed AI semantic acceptance',freshness='Preserves saved company as-of date; FX has its own explicit snapshot time; use update to discover newer company releases')
        from ..shared_artifacts import integrated_runtime_fingerprint
        record['configuration']['runtime']=integrated_runtime_fingerprint()
        from ..shared_artifacts import code_snapshot
        write_json(directory/'code_snapshot.json',code_snapshot())
        latest_reviews={}
        for call in previous.get('calls',[]):
            if call.get('stage','').startswith('integrated_') and call.get('result') and not call.get('error'):
                latest_reviews[call['stage']]={key:call.get(key) for key in ('call_id','model','reasoning_effort','result','usage')}
        write_json(directory/'review_routes.json',dict(mode='Preserved completed reviews; no AI calls during this operation',stages=latest_reviews))
        if fx:write_json(directory/'fx_import.json',{k:fx[k] for k in ('source','metadata','policy','findings') if k in fx} if fx_database else fx)
        if refresh_audit:write_json(directory/'fx_refresh_audit.json',refresh_audit)
        from ..historic_construction.evidence import source_selection_audit
        write_json(directory/'source_selection_audit.json',source_selection_audit(data,spec,frozen,values))
        for name,value in [('company_model_inputs.json',data),('model_specification.json',spec),('forecast.json',values),('validation.json',dict(status=status,financial_completeness=spec['financial_completeness'],checks=checks,gaps=spec['gaps'])),('workbook_validation.json',inspection)]:write_json(directory/name,value)
        write_json(directory/'input_contract.json',spec['input_contract'])
        if spec.get('assumption_payload'):write_json(directory/'assumptions.json',spec['assumption_payload'])
        shutil.copyfile(prior/'calls.jsonl',directory/'calls.jsonl')
        for file in directory.iterdir():
            if file.is_file():record['artifacts'][file.name]=hashlib.sha256(file.read_bytes()).hexdigest()
        write_json(directory/'record.json',record)
        if progress:progress('Offline export: zero AI calls. '+str(directory))
        return directory

