<?php
// Test doubles only. Production code uses the inspected Espo10.0.11 interfaces/ORM.
namespace Espo\Core\Exceptions {class BadRequest extends \Exception {} class Forbidden extends \Exception {} class Conflict extends \Exception {} class NotFound extends \Exception {}}
namespace Espo\Core\Utils {
 class Metadata {public function __construct(private array $data){} public function get($path){$node=$this->data;foreach($path as $key){if(!is_array($node) || !array_key_exists($key,$node))return null;$node=$node[$key];}return $node;}}
}
namespace Espo\Core\Api {
 interface Request {} interface Action {public function process(Request $request):Response;}
 class Response {public function __construct(public $data){} public function setHeader($k,$v){return $this;}}
 class ResponseComposer {public static function json($data):Response{return new Response($data);}}
}
namespace Espo\Core\Console {interface Command {public function run(Command\Params $params,IO $io):void;} class IO {public array $lines=[];public function writeLine($s){$this->lines[]=$s;}}}
namespace Espo\Core\Console\Command {class Params {public function getArgumentList(){return [];}}}
namespace Espo\ORM {interface Entity {public function clear(string $attribute):void;public function getEntityType():string;}}
namespace Espo\Core\Record\Output {interface Filter {public function filter(\Espo\ORM\Entity $entity):void;}}
namespace Espo\Core\ORM {
 class Row implements \Espo\ORM\Entity {
  public function clear(string $attribute):void {unset($this->data[$attribute]);}public function getEntityType():string{return $this->type;}
  public array $data=[];public function __construct(public string $type){}
  public function get($k){return $this->data[$k]??null;}public function getId(){return $this->get('id');}
  public function set($k,$v=null){if(is_array($k))$this->data=array_merge($this->data,$k);else $this->data[$k]=$v;return $this;}
 }
 class EntityManager {
  public array $rows=[];public int $writes=0;public int $locks=0;public bool $failReceipt=false;
  public function getEntityById($type,$id){return $this->rows[$type][$id]??null;}
  public function getNewEntity($type){return new Row($type);}
  public function saveEntity($row,$options=[]){
   if($row->type==='Contact' && ($options['skipHooks']??false)!==true)throw new \RuntimeException('synthetic control must skip business hooks');
   if($row->type==='UniqueId' && $this->failReceipt)throw new \RuntimeException('synthetic receipt failure');
   if(!$row->getId())$row->set('id',str_pad((string)(count($this->rows['Contact']??[])+1),17,'0',STR_PAD_LEFT));
   if($row->type==='Contact'){$this->writes++;$row->set('modifiedAt','synthetic-'.$this->writes);}
   $this->rows[$row->type][$row->getId()]=$row;
  }
  public function getRDBRepository($type){return new class($this,$type){
   public array $where=[];public function __construct(private $em,private $type){}
   public function where($where){$this->where=$where;return $this;}public function forUpdate(){$this->em->locks++;return $this;}
   public function findOne(){return $this->em->getEntityById($this->type,$this->where['id']);}
  };}
  public function getTransactionManager(){return new class($this){
   public function __construct(private $em){}
   public function run($fn){$snapshot=serialize($this->em->rows);$writes=$this->em->writes;try{return $fn();}catch(\Throwable $e){$this->em->rows=unserialize($snapshot);$this->em->writes=$writes;throw $e;}}
  };}
 }
}
namespace {
 use Espo\Core\ORM\EntityManager;use Espo\Core\Exceptions\{BadRequest,Forbidden,Conflict,NotFound};
 use Espo\Modules\OpenTourControl\Services\TitleControl;use Espo\Modules\OpenTourControl\Api\Title;use Espo\Modules\OpenTourControl\Console\Bootstrap;
 $module=dirname(__DIR__,2).'/extensions/espo-control/custom/Espo/Modules/OpenTourControl';
 require $module.'/Services/TitleControl.php';require $module.'/Services/FirstNameControl.php';require $module.'/Api/Title.php';require $module.'/Api/FirstName.php';require $module.'/Console/Bootstrap.php';
 require $module.'/Record/Output/ControlField.php';
 $checks=[];
 function check($name,$condition){global $checks;if(!$condition)throw new \RuntimeException('failed '.$name);$checks[]=$name;}
 function denied($name,$class,$fn){try{$fn();}catch(\Throwable $error){check($name,$error instanceof $class);return;}throw new \RuntimeException('not denied '.$name);}
 function privateFile($path,$data){file_put_contents($path,json_encode($data));chmod($path,0600);}
 $temp=sys_get_temp_dir().'/opentour-capability-test-'.bin2hex(random_bytes(6));mkdir($temp,0700);mkdir($temp.'/data',0700);chdir($temp);
 $metadata=new \Espo\Core\Utils\Metadata(['entityDefs'=>['Contact'=>json_decode(file_get_contents($module.'/Resources/metadata/entityDefs/Contact.json'),true)]]);
 $em=new EntityManager();$token=str_repeat('syntheticToken',4);$nonce=str_repeat('syntheticNonce',4);
 try {
  $control=new TitleControl($em,$metadata);
  denied('missing-storage-metadata-denies',Forbidden::class,fn()=>new TitleControl($em,new \Espo\Core\Utils\Metadata([])));
  denied('missing-config-denies',Forbidden::class,fn()=>$control->authorize($token));
  privateFile('data/opentour-control-bootstrap.json',(object)['nonce'=>$nonce,'token'=>$token]);
  $bootstrap=new Bootstrap($em,$metadata);$io=new \Espo\Core\Console\IO();$params=new \Espo\Core\Console\Command\Params();
  $em->failReceipt=true;denied('bootstrap-receipt-failure-rolls-back',\RuntimeException::class,fn()=>$bootstrap->run($params,$io));$em->failReceipt=false;
  check('bootstrap-failure-created-no-contact',empty($em->rows['Contact']));
  $bootstrap->run($params,$io);$bootstrap->run($params,$io);
  check('bootstrap-retry-creates-one-contact',count($em->rows['Contact'])===1 && $em->writes===1);
  check('bootstrap-never-emits-token',!str_contains(implode('',$io->lines),$token));
  privateFile('data/opentour-control-bootstrap.json',(object)['nonce'=>str_repeat('differentNonce',4),'token'=>$token]);
  denied('new-nonce-cannot-create-second-control',Conflict::class,fn()=>$bootstrap->run($params,$io));
  check('conflicting-bootstrap-left-one-contact',count($em->rows['Contact'])===1);
  privateFile('data/opentour-control-bootstrap.json',(object)['nonce'=>$nonce,'token'=>$token]);
  $config=$control->authorize($token);$initial=$control->read($config);
  $metadata=json_decode(file_get_contents($module.'/Resources/metadata/entityDefs/Contact.json'),true);
  check('explicit-storable-control-field',$metadata['fields'][TitleControl::FIELD]['type']==='varchar' && $metadata['fields'][TitleControl::FIELD]['notStorable']===false && $metadata['fields'][TitleControl::FIELD]['maxLength']===100);
  check('native-title-metadata-not-overridden',!isset($metadata['fields']['title']));
  check('bootstrap-pins-generated-synthetic-record',$initial['id']===$config->contactId && $initial['title']==='');
  denied('wrong-capability-denies',Forbidden::class,fn()=>$control->authorize(str_repeat('x',40)));
  chmod('data/opentour-control.json',0644);denied('nonprivate-config-denies',Forbidden::class,fn()=>$control->authorize($token));chmod('data/opentour-control.json',0600);
  $edit=(object)['operationId'=>str_repeat('a',64),'baseVersion'=>$initial['version'],'title'=>'Synthetic title','actor'=>'synthetic-app-admin'];
  foreach(['entity','id','description','status','host','command'] as $field){$bad=clone $edit;$bad->$field='forged';denied('extra-'.$field.'-denies',BadRequest::class,fn()=>$control->edit($config,$bad));}
  foreach([str_repeat('x',101),"bad\nvalue",123] as $value){$bad=clone $edit;$bad->title=$value;denied('invalid-title-'.count($checks),BadRequest::class,fn()=>$control->edit($config,$bad));}
  $saved=$control->edit($config,$edit);$replayed=$control->edit($config,$edit);
  check('exact-retry-one-write',$saved===$replayed && $em->writes===2 && $em->locks>=2);
  check('status-reconciles-committed-result',$control->status($config,$edit->operationId)===$saved);
  check('read-reloads-title',$control->read($config)['title']==='Synthetic title');
  $filter=new \Espo\Modules\OpenTourControl\Record\Output\ControlField();
  $projection=clone $em->getEntityById('Contact',$config->contactId);$projection->set('title','Native relationship role');
  $beforeProjection=$projection->data;$filter->filter($projection);unset($beforeProjection[TitleControl::FIELD]);
  check('generic-output-removes-only-control-field',$projection->data===$beforeProjection);
  check('filter-does-not-change-stored-control',$control->read($config)['title']==='Synthetic title');
  $other=new \Espo\Core\ORM\Row('Account');$other->set(TitleControl::FIELD,'unrelated');$filter->filter($other);
  check('filter-does-not-change-other-entity',$other->get(TitleControl::FIELD)==='unrelated');
  $acl=json_decode(file_get_contents($module.'/Resources/metadata/app/acl.json'),true);
  foreach(['mandatory','adminMandatory'] as $kind){
   check($kind.'-denies-only-control-field',$acl[$kind]===['scopeFieldLevel'=>['Contact'=>[TitleControl::FIELD=>['read'=>'no','edit'=>'no']]]]);
  }
  $record=json_decode(file_get_contents($module.'/Resources/metadata/recordDefs/Contact.json'),true);
  check('generic-filter-appends-without-replacing-native-filters',$record===['outputFilterClassNameList'=>['__APPEND__',\Espo\Modules\OpenTourControl\Record\Output\ControlField::class]]);

  $bad=clone $edit;$bad->title='Changed same key';denied('changed-same-operation-conflicts',Conflict::class,fn()=>$control->edit($config,$bad));
  $bad=clone $edit;$bad->operationId=str_repeat('b',64);denied('stale-version-conflicts',Conflict::class,fn()=>$control->edit($config,$bad));
  $bad=clone $edit;$bad->operationId=str_repeat('c',64);$bad->baseVersion=$saved['version'];$bad->title='Must roll back';$em->failReceipt=true;
  denied('receipt-failure-rolls-back',\RuntimeException::class,fn()=>$control->edit($config,$bad));$em->failReceipt=false;
  check('failed-receipt-did-not-commit-title',$control->read($config)['title']==='Synthetic title');
  $foreign=clone $config;$foreign->contactId='00000000000009999';denied('foreign-pinned-record-denies',Forbidden::class,fn()=>$control->read($foreign));
  $wrongMarker=clone $config;$wrongMarker->marker='opentour-synthetic-control:'.str_repeat('0',64);denied('unmarked-owner-record-denies',Forbidden::class,fn()=>$control->read($wrongMarker));
  class Req implements \Espo\Core\Api\Request {
   public array $headers=[];public array $query=[];public string $method='GET';public $body;public ?string $operation=null;
   public function hasHeader($key){return isset($this->headers[$key]);}public function getHeader($key){return $this->headers[$key]??null;}
   public function getHeaderAsArray($key){return isset($this->headers[$key])?[$this->headers[$key]]:[];}
   public function getQueryParams(){return $this->query;}public function getMethod(){return $this->method;}public function getRouteParam($key){return $this->operation;}
   public function getBodyContents(){return json_encode($this->body);}public function getParsedBody(){return $this->body;}
  }
  $api=new Title($control);$request=new Req();$request->headers=['X-OpenTour-Control'=>$token];
  check('capability-api-read-only-pinned-fields',array_keys($api->process($request)->data)===['entity','id','field','title','version']);
  foreach(['X-Api-Key','Authorization','Espo-Authorization','X-Hmac-Authorization'] as $header){$bad=clone $request;$bad->headers[$header]='synthetic-native-auth';denied('native-auth-'.$header.'-denies',Forbidden::class,fn()=>$api->process($bad));}
  $bad=clone $request;$bad->query=['entity'=>'Account'];denied('query-overrides-deny',Forbidden::class,fn()=>$api->process($bad));
  $bad=clone $request;$bad->method='DELETE';denied('delete-denies',Forbidden::class,fn()=>$api->process($bad));
  $bad=clone $request;$bad->headers=[];denied('missing-capability-header-denies',Forbidden::class,fn()=>$api->process($bad));
  $nativeMetadata=new \Espo\Core\Utils\Metadata(['entityDefs'=>['Contact'=>['fields'=>['firstName'=>['type'=>'varchar','maxLength'=>100]]]]]);
  $names=new \Espo\Modules\OpenTourControl\Services\FirstNameControl($em,$nativeMetadata);
  $contact=$em->getEntityById('Contact',$config->contactId);$contact->set('firstName','Fictional');$contact->set('title','Relationship role');
  $beforeName=$contact->data;$nameBase=$names->read($config);
  $nameBody=(object)['operationId'=>$edit->operationId,'firstName'=>'Synthetic revised','baseVersion'=>$nameBase['version'],'actor'=>'synthetic-app-admin'];
  denied('label-receipt-not-native-name-receipt',NotFound::class,fn()=>$names->status($config,$edit->operationId));
  $nameSaved=$names->edit($config,$nameBody);
  check('native-name-fixed-field-saved',$nameSaved['field']==='firstName' && $nameSaved['firstName']==='Synthetic revised');
  check('native-name-replay-stable',$names->edit($config,$nameBody)===$nameSaved);
  $freshNames=new \Espo\Modules\OpenTourControl\Services\FirstNameControl($em,$nativeMetadata);
  check('native-name-fresh-service-read',$freshNames->read($config)['firstName']==='Synthetic revised');
  check('name-edit-preserves-label-marker-and-role',$contact->get('description')===$beforeName['description'] && $contact->get('title')===$beforeName['title'] && $contact->get(TitleControl::FIELD)===$beforeName[TitleControl::FIELD]);
  foreach(['', '   ', str_repeat('x',101),"bad\nname"] as $value){$bad=clone $nameBody;$bad->firstName=$value;denied('bad-native-name-'.count($checks),BadRequest::class,fn()=>$names->edit($config,$bad));}
  $bad=clone $nameBody;$bad->field='description';denied('caller-native-field-denied',BadRequest::class,fn()=>$names->edit($config,$bad));
  $bad=clone $nameBody;$bad->firstName='Changed same key';denied('native-name-key-conflict',Conflict::class,fn()=>$names->edit($config,$bad));
  $bad=clone $nameBody;$bad->operationId=str_repeat('d',64);denied('native-name-stale-conflict',Conflict::class,fn()=>$names->edit($config,$bad));
  $nativeApi=new \Espo\Modules\OpenTourControl\Api\FirstName($names);
  check('native-action-fixed-field-read',$nativeApi->process($request)->data['field']==='firstName');
  $bad=clone $nameBody;$bad->operationId=str_repeat('e',64);$bad->baseVersion=$nameSaved['version'];$bad->firstName='Must roll back';$em->failReceipt=true;
  denied('native-name-receipt-failure-rolls-back',\RuntimeException::class,fn()=>$names->edit($config,$bad));$em->failReceipt=false;
  check('native-name-rollback-preserves-field',$names->read($config)['firstName']==='Synthetic revised');
  $routes=json_decode(file_get_contents($module.'/Resources/routes.json'),true);
  check('only-six-fixed-upstream-routes',count($routes)===6 && count(array_unique(array_column($routes,'actionClassName')))===2);

  echo json_encode(['mode'=>'SYNTHETIC PHP STUBS','checks'=>count($checks),'passed'=>$checks,'actualEspoORMIntegration'=>'NOT RUN']).PHP_EOL;
 } finally {foreach(glob($temp.'/data/*') as $file)unlink($file);rmdir($temp.'/data');chdir('/tmp');rmdir($temp);}
}
