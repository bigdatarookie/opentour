<?php
/** QA-owned real Espo fixture only. No manual SQL/DDL or owner services. */
if (getenv('OPENTOUR_DISPOSABLE_CRM_TEST')!=='opentour-pr24-qa-20261114-8fd750') {
    fwrite(STDERR,"Explicit QA fixture acknowledgement required.\n");exit(2);
}
require '/var/www/html/bootstrap.php';

use Espo\Core\Application;
use Espo\Core\Console\Command\Params;
use Espo\Core\Console\IO;
use Espo\Core\Exceptions\NotFound;
use Espo\Modules\OpenTourControl\Console\Bootstrap;
use Espo\Modules\OpenTourControl\Services\TitleControl;

$checks=[];
function checkStorage(string $name,bool $ok): void {
    global $checks;if(!$ok)throw new RuntimeException('check:'.$name);$checks[]=$name;
}
function businessValues($entity): array {
    $map=(array)$entity->getValueMap();
    foreach ([TitleControl::FIELD,'modifiedAt','modifiedById','modifiedByName'] as $key)unset($map[$key]);
    ksort($map);return $map;
}
try {
    $app=new Application();$app->setupSystemUser();$container=$app->getContainer();$em=$container->get('entityManager');
    $metadata=$container->get('metadata');
    checkStorage('custom-field-declared-storable',$metadata->get(['entityDefs','Contact','fields',TitleControl::FIELD,'notStorable'])===false);
    checkStorage('native-title-still-nonstorable',$metadata->get(['entityDefs','Contact','fields','title','notStorable'])===true);
    checkStorage('custom-field-bounded-varchar',$metadata->get(['entityDefs','Contact','fields',TitleControl::FIELD,'type'])==='varchar' && $metadata->get(['entityDefs','Contact','fields',TitleControl::FIELD,'maxLength'])===100);
    // This exact private fixture has one already-marked bootstrap Contact, no owner data.
    checkStorage('fixture-has-exactly-one-control-contact',$em->getRDBRepository('Contact')->count()===1);
    $writer=TitleControl::privateJson('data/opentour-control-writer.json');
    $control=new TitleControl($em,$metadata);$config=$control->authorize($writer->token);
    $contact=$em->getEntityById('Contact',$config->contactId);
    checkStorage('fixture-marker-matches',$contact && $contact->get('description')===$config->marker);
    $io=new class extends IO {public array $results=[];public function writeLine(string $line): void {$this->results[]=json_decode($line,true,16,JSON_THROW_ON_ERROR);}};
    $bootstrap=new Bootstrap($em,$metadata);$params=new Params([],[],[]);
    $bootstrap->run($params,$io);$bootstrap->run($params,$io);
    checkStorage('bootstrap-repeat-retains-one-exact-contact',count($io->results)===2 && $io->results[0]['contactId']===$config->contactId && $io->results[1]['contactId']===$config->contactId && $em->getRDBRepository('Contact')->count()===1);

    $legacyCount=0;
    foreach ($em->getRDBRepository('UniqueId')->find() as $receipt) {
        $name=$receipt->get('name') ?? '';
        if (preg_match('/^OpenTourControlTitle:([a-f0-9]{64})$/D',$name,$match)) {
            $legacyCount++;
            try {$result=$control->status($config,$match[1]);checkStorage('legacy-status-is-explicitly-new-field',($result['field']??null)===TitleControl::FIELD);}
            catch (NotFound $ignored) {} // A legacy virtual-title receipt cannot satisfy the new namespace.
        }
    }
    checkStorage('legacy-receipt-preserved-not-reused',$legacyCount>=1);

    $accountMarker='opentour-storage-regression:'.$config->contactId;
    $accounts=$em->getRDBRepository('Account');
    $account=$accounts->where(['description'=>$accountMarker])->findOne();
    checkStorage('no-unrelated-account-in-fixture',$accounts->count()===($account ? 1 : 0));
    if (!$account) {
        $account=$em->getNewEntity('Account');
        $account->set(['name'=>'SYNTHETIC OPENTOUR STORAGE REGRESSION','description'=>$accountMarker]);
        $em->saveEntity($account,['skipHooks'=>true]);
    }
    $relation=$em->getRDBRepository('Contact')->getRelation($contact,'accounts');
    if (!$relation->isRelated($account))$relation->relate($account,['role'=>'SYNTHETIC RELATION ROLE'],['skipHooks'=>true]);
    if (!$contact->get('accountId')) {$contact->set('accountId',$account->getId());$em->saveEntity($contact,['skipHooks'=>true]);}
    checkStorage('primary-account-is-the-fixture',$contact->get('accountId')===$account->getId());
    $contact=$em->getEntityById('Contact',$config->contactId);
    $roleBefore=$em->getRDBRepository('Contact')->getRelation($contact,'accounts')->getColumn($account,'role');
    checkStorage('nonempty-native-role-baseline',$roleBefore==='SYNTHETIC RELATION ROLE' && $contact->get('title')===$roleBefore);
    $businessBefore=businessValues($contact);$accountBefore=businessValues($em->getEntityById('Account',$account->getId()));
    $requestFile='data/opentour-control-storage-regression-request.json';
    if (file_exists($requestFile))$body=TitleControl::privateJson($requestFile);
    else {
        $snapshot=$control->read($config);
        $body=(object)['operationId'=>bin2hex(random_bytes(32)),'baseVersion'=>$snapshot['version'],'title'=>'SYNTHETIC STORED CONTROL LABEL','actor'=>'synthetic-storage-regression'];
        $oldMask=umask(0077);$stream=fopen($requestFile,'x');umask($oldMask);
        fwrite($stream,json_encode($body,JSON_THROW_ON_ERROR)."\n");fflush($stream);fsync($stream);fclose($stream);
    }
    checkStorage('regression-request-is-fixed-synthetic-input',$body->actor==='synthetic-storage-regression' && $body->title==='SYNTHETIC STORED CONTROL LABEL');
    $saved=$control->edit($config,$body);
    checkStorage('saved-response-names-real-field',$saved['field']===TitleControl::FIELD && $saved['title']===$body->title && $saved['saved']===true);

    // Fresh application/EntityManager forces a genuine database reload, not the edited object cache.
    $freshApp=new Application();$freshApp->setupSystemUser();$freshEm=$freshApp->getContainer()->get('entityManager');
    $freshControl=new TitleControl($freshEm,$freshApp->getContainer()->get('metadata'));$freshConfig=$freshControl->authorize($writer->token);
    $fresh=$freshEm->getEntityById('Contact',$config->contactId);
    $read=$freshControl->read($freshConfig);
    checkStorage('custom-value-survives-fresh-orm-read',$fresh->get(TitleControl::FIELD)===$body->title && $read['title']===$body->title && $read['field']===TitleControl::FIELD);
    checkStorage('native-role-untouched',$fresh->get('title')===$roleBefore && $freshEm->getRDBRepository('Contact')->getRelation($fresh,'accounts')->getColumnById($account->getId(),'role')===$roleBefore);
    checkStorage('unrelated-contact-fields-unchanged',businessValues($fresh)===$businessBefore);
    checkStorage('unrelated-account-fields-unchanged',businessValues($freshEm->getEntityById('Account',$account->getId()))===$accountBefore);
    $countAfter=$freshEm->getRDBRepository('UniqueId')->count();$valuesBeforeReplay=(array)$fresh->getValueMap();
    $replay=$freshControl->edit($freshConfig,$body);
    checkStorage('exact-replay-returns-same-receipt',$replay==$saved && $freshEm->getRDBRepository('UniqueId')->count()===$countAfter);
    checkStorage('exact-replay-changes-no-contact-fields',(array)$freshEm->getEntityById('Contact',$config->contactId)->getValueMap()===$valuesBeforeReplay);
    echo json_encode(['mode'=>'REAL DISPOSABLE ESPO10.0.11 ORM','field'=>TitleControl::FIELD,'passed'=>count($checks),'checks'=>$checks,'legacyReceiptsPreserved'=>$legacyCount,'controlContacts'=>1,'fixtureAccounts'=>1,'ownerServices'=>false],JSON_THROW_ON_ERROR).PHP_EOL;
} catch (Throwable $error) {
    $message=$error->getMessage();
    echo json_encode(['mode'=>'REAL DISPOSABLE ESPO10.0.11 ORM','error'=>str_starts_with($message,'check:')?$message:'orm_regression_error','exception'=>get_class($error),'passed'=>count($checks),'checks'=>$checks]).PHP_EOL;
    exit(1);
}
