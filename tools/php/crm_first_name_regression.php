<?php
/** Independent QA-owned synthetic Espo only; never owner runtime. */
if (getenv('OPENTOUR_DISPOSABLE_CRM_TEST')!=='opentour-first-name-qa') {
    fwrite(STDERR,"Explicit disposable QA acknowledgement required.\n");exit(2);
}
require '/var/www/html/bootstrap.php';
use Espo\Core\Application;
use Espo\Modules\OpenTourControl\Services\{TitleControl,FirstNameControl};
$checks=[];
function verifyName(string $name,bool $ok): void {
    global $checks;if(!$ok)throw new RuntimeException('check:'.$name);$checks[]=$name;
}
function nameBusiness($row): array {
    $map=(array)$row->getValueMap();
    // Native name is computed from firstName/lastName; audit fields change normally.
    foreach(['firstName','name','modifiedAt','modifiedById','modifiedByName'] as $key)unset($map[$key]);
    ksort($map);return $map;
}
try {
    $app=new Application();$app->setupSystemUser();$c=$app->getContainer();$em=$c->get('entityManager');
    verifyName('exactly-one-synthetic-contact',$em->getRDBRepository('Contact')->count()===1);
    $writer=TitleControl::privateJson('data/opentour-control-writer.json');
    $control=new FirstNameControl($em,$c->get('metadata'));$config=$control->authorize($writer->token);
    $row=$em->getEntityById('Contact',$config->contactId);
    verifyName('marker-bound-before-write',$row && $row->get('description')===$config->marker);
    $requestFile='data/opentour-first-name-regression.json';
    if (file_exists($requestFile))$savedInput=TitleControl::privateJson($requestFile);
    else {
        $savedInput=(object)['before'=>(object)nameBusiness($row),'body'=>(object)[
            'operationId'=>bin2hex(random_bytes(32)),'firstName'=>'Fictional Revised',
            'baseVersion'=>$control->read($config)['version'],'actor'=>'synthetic-first-name-qa']];
        $mask=umask(0077);$file=fopen($requestFile,'x');umask($mask);
        fwrite($file,json_encode($savedInput,JSON_THROW_ON_ERROR));fflush($file);fsync($file);fclose($file);
    }
    $body=$savedInput->body;
    verifyName('stable-fictional-input',$body->actor==='synthetic-first-name-qa' && $body->firstName==='Fictional Revised');
    $result=$control->edit($config,$body);
    $freshApp=new Application();$freshApp->setupSystemUser();$fc=$freshApp->getContainer();$freshEm=$fc->get('entityManager');
    $fresh=new FirstNameControl($freshEm,$fc->get('metadata'));$freshConfig=$fresh->authorize($writer->token);
    $stored=$freshEm->getEntityById('Contact',$config->contactId);
    verifyName('fresh-orm-native-field-persists',$stored->get('firstName')===$body->firstName);
    verifyName('fresh-capability-read-persists',$fresh->read($freshConfig)['firstName']===$body->firstName && $result['field']==='firstName');
    verifyName('native-display-name-reflects-edit',str_contains($stored->get('name') ?? '',$body->firstName));
    verifyName('marker-label-role-other-fields-preserved',nameBusiness($stored)===(array)$savedInput->before);
    $count=$freshEm->getRDBRepository('UniqueId')->count();$values=(array)$stored->getValueMap();
    verifyName('same-key-replay-same-receipt',$fresh->edit($freshConfig,$body)===$result);
    verifyName('replay-no-extra-receipt',$freshEm->getRDBRepository('UniqueId')->count()===$count);
    verifyName('replay-no-contact-mutation',(array)$freshEm->getEntityById('Contact',$config->contactId)->getValueMap()===$values);
    echo json_encode(['mode'=>'REAL DISPOSABLE ESPO ORM','checks'=>$checks,'passed'=>count($checks),'ownerServices'=>false]).PHP_EOL;
} catch (Throwable $error) {
    echo json_encode(['error'=>str_starts_with($error->getMessage(),'check:')?$error->getMessage():'native_name_qa_error','exception'=>get_class($error),'checks'=>$checks]).PHP_EOL;exit(1);
}
