"""One-shot disposable-fixture matrix. Runtime is explicit; owner endpoint is refused."""
import argparse,contextlib,copy,hashlib,io,json,stat,subprocess,sys,tempfile,types,urllib.error,urllib.parse,urllib.request,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import contact_import as imp
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime-file',type=Path,required=True,help='Private disposable synthetic API config; owner port18082 refused')
args=parser.parse_args()
runtime_path=args.runtime_file
if stat.S_IMODE(runtime_path.stat().st_mode)&0o077: raise RuntimeError('runtime_file_not_private')
cfg=json.loads(runtime_path.read_text())
# Config schema is supplied by task env owner; no fallback to owner constants.
base=cfg['api'].rstrip('/')
u=urllib.parse.urlsplit(base)
if u.scheme!='http' or u.hostname!='127.0.0.1' or u.port in (None,18082) or u.path!='/api/v1' or u.username or u.password or u.query or u.fragment:
 raise RuntimeError('isolated_target_required')
if cfg.get('syntheticOnly') is not True: raise RuntimeError('synthetic_attestation_required')
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs): return None
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
headers=cfg['headers']
observed=[]
def open_fixture(req,timeout=30):
 if not req.full_url.startswith(base+'/'): raise RuntimeError('outside_fixture')
 try:
  response=opener.open(req,timeout=timeout)
  observed.append({'method':req.method,'path':urllib.parse.urlsplit(req.full_url).path,'status':response.status})
  return response
 except urllib.error.HTTPError as exc:
  raw=exc.read(1024*1024)
  try: payload=json.loads(raw)
  except (ValueError,UnicodeDecodeError): payload=None
  allowed_reasons={'Duplicate','duplicate','Conflict','duplicateEntry','validationFailure'}
  reason=exc.headers.get('X-Status-Reason')
  if reason not in allowed_reasons: reason=None
  detail=(payload or {}).get('messageTranslation',{}) if isinstance(payload,dict) else {}
  detail=detail.get('data',{}) if isinstance(detail,dict) else {}
  field=detail.get('field') if isinstance(detail,dict) else None
  kind=detail.get('type') if isinstance(detail,dict) else None
  observed.append({'method':req.method,'path':urllib.parse.urlsplit(req.full_url).path,'status':exc.code,
   'reason':reason,'field':field if field in imp.CRM_ERROR_FIELD_ALLOWLIST else None,
   'type':kind if kind in imp.CRM_ERROR_TYPE_ALLOWLIST|{'valid','maxCount'} else None})
  raise urllib.error.HTTPError(req.full_url,exc.code,'fixture error',exc.headers,io.BytesIO(raw)) from None
crm=imp.CRM.__new__(imp.CRM);crm.headers=headers
run=hashlib.sha256(uuid.uuid4().bytes).hexdigest()
def row(n,phone=None,email=None):
 return {'source_ordinal':1,'logical_row':n,'source_revision':run,'mapping_version':'synthetic-v011',
  'workbook_alias':None,'sheet_alias':None,'surname_status':'placeholder_none','last_name':'None',
  'email_raw':email,'email_key':email.casefold() if email else None,'phone_raw':phone,'phone_key':phone,
  'normalized_phone':phone,'phone_normalization_version':'e164-default-7-v1','disposition':'candidate'}
def count():
 search={'select':['id'],'maxSize':1,'offset':0}
 _,data=crm.call('GET','/Contact?'+urllib.parse.urlencode({'searchParams':json.dumps(search)}))
 return data['total']
def post_case(name,r):
 before=count();start=len(observed)
 try:
  status,obj=crm.call('POST','/Contact',imp.build_contact_body(r));outcome='created' if obj.get('id') else 'response_without_id'
 except imp.ImportFailure as exc:
  status=next((x['status'] for x in reversed(observed[start:]) if x['method']=='POST'),None);outcome=exc.code
 after=count()
 error=next((x for x in reversed(observed[start:]) if x['method']=='POST'),{})
 return {'case':name,'status':status,'reason':error.get('reason'),'field':error.get('field'),'type':error.get('type'),
         'records_before':before,'records_after':after,'outcome':outcome}
with patch.object(imp,'API',base),patch.object(imp.urllib.request,'urlopen',side_effect=open_fixture):
 initial=count()
 if initial!=0: raise RuntimeError('fresh_fixture_not_empty')
 results=[]
 baseline=row(1,phone='+12025550101')
 results.append(post_case('unique_marker_phone_baseline',baseline))
 results.append(post_case('same_phone_different_marker',row(2,phone='+12025550101')))
 repeated=copy.deepcopy(baseline);repeated.update(phone_raw='+12025550102',phone_key='+12025550102',normalized_phone='+12025550102')
 results.append(post_case('different_phone_repeated_marker',repeated))
 email=row(4,email='synthetic-'+run[:12]+'@example.invalid')
 mapping={'mapping_version':'synthetic-v011','import_authorization':'bounded first import to selected local EspoCRM explicitly assigned by qitem-20261108184715-500ad3de; no external writes'}
 quality=types.SimpleNamespace(PHONE_NORMALIZATION_VERSION='e164-default-7-v1',require_private_mapping=lambda _:mapping)
 with tempfile.TemporaryDirectory(prefix='opentour-synthetic-import-state-') as temp:
  private=Path(temp)
  with patch.object(imp,'PRIVATE_DIR',private),patch.object(imp,'MAPPING_PATH',private/'mapping.json'),patch.object(imp,'CHECKPOINT_PATH',private/'checkpoint.json'),patch.object(imp,'EVENTS_PATH',private/'events.jsonl'),patch.object(imp,'load_quality_module',return_value=quality),patch.object(imp,'source_records',return_value=[email]),patch.object(imp,'CRM',return_value=crm),patch.object(sys,'argv',['synthetic-import']):
   for name in ('email_only_importer','exact_source_checkpoint_repeat'):
    before=count();start=len(observed);capture=io.StringIO()
    with contextlib.redirect_stdout(capture): exit_code=imp.main()
    summary=json.loads(capture.getvalue())
    results.append({'case':name,'status':next((x['status'] for x in reversed(observed[start:]) if x['method']=='POST'),None),
     'records_before':before,'records_after':count(),'outcome':summary.get('aggregate_dispositions',summary),
     'exit_code':exit_code,'post_count':sum(x['method']=='POST' for x in observed[start:])})
 print(json.dumps({'mode':'SYNTHETIC ONLY','base_source':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),'results':results,'owner_target_used':False,'owner_input_used':False,'synthetic_private_state_removed':True}))
