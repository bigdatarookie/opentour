<?php
namespace Espo\Modules\OpenTourControl\Console;
use Espo\Core\Console\{Command,IO};
use Espo\Core\Console\Command\Params;
use Espo\Core\ORM\EntityManager;
use Espo\Core\Exceptions\{Forbidden,Conflict};
use Espo\Modules\OpenTourControl\Services\TitleControl;

/** Explicit OS-operator command; no web create endpoint and no admin password/API key. */
class Bootstrap implements Command
{
    public function __construct(private EntityManager $em) {}
    private function writePrivate(string $path, object $data): void
    {
        if (file_exists($path)) {
            if (TitleControl::privateJson($path)!=$data) throw new Conflict('control_file_already_differs');
            return;
        }
        $temporary=$path.'.'.bin2hex(random_bytes(8)).'.tmp';
        $stream=fopen($temporary,'x');chmod($temporary,0600);
        try {fwrite($stream,json_encode($data,JSON_THROW_ON_ERROR)."\n");fflush($stream);fsync($stream);} finally {fclose($stream);}
        if (file_exists($path)) {unlink($temporary);throw new Conflict('control_file_created_concurrently');}
        if (!link($temporary,$path)) {unlink($temporary);throw new Conflict('control_file_publish_failed');}
        unlink($temporary);
    }
    public function run(Params $params, IO $io): void
    {
        if ($params->getArgumentList()) throw new Forbidden('control_bootstrap_no_arguments');
        $input=TitleControl::privateJson('data/opentour-control-bootstrap.json');
        TitleControl::exact($input,['nonce','token']);
        foreach ([$input->nonce,$input->token] as $value) {
            if (!is_string($value) || !preg_match('/^[A-Za-z0-9_-]{32,128}$/D',$value)) throw new Forbidden('control_bootstrap_invalid');
        }
        $name='OpenTourControlBootstrap:'.hash('sha256',$input->nonce);
        $id=substr(hash('sha256',$name),0,17);
        $marker='opentour-synthetic-control:'.hash('sha256',$input->nonce);
        $tokenHash=hash('sha256',$input->token);
        $contactId=$this->em->getTransactionManager()->run(function() use($id,$name,$marker,$tokenHash) {
            $prior=$this->em->getEntityById('UniqueId',$id);
            if ($prior) {
                $data=$prior->get('data');
                if ($prior->get('name')!==$name || ($data->tokenSha256 ?? null)!==$tokenHash) throw new Conflict('control_bootstrap_conflict');
                $contact=$this->em->getEntityById('Contact',$data->contactId);
                if (!$contact || $contact->get('description')!==$marker) throw new Conflict('control_bootstrap_record_changed');
                return $contact->getId();
            }
            if (file_exists('data/opentour-control.json') || file_exists('data/opentour-control-writer.json')) throw new Conflict('control_already_bootstrapped');
            $contact=$this->em->getNewEntity('Contact');
            $contact->set(['firstName'=>'OpenTour','lastName'=>'SYNTHETIC CONTROL','description'=>$marker,'title'=>'']);
            $this->em->saveEntity($contact,['skipHooks'=>true]); // Synthetic control: suppress unrelated business hooks; normal audit timestamps remain.
            $receipt=$this->em->getNewEntity('UniqueId');$receipt->set('id',$id);$receipt->set('name',$name);
            $receipt->set('data',(object)['tokenSha256'=>$tokenHash,'contactId'=>$contact->getId()]);
            $this->em->saveEntity($receipt);
            return $contact->getId();
        });
        $this->writePrivate('data/opentour-control.json',(object)['contactId'=>$contactId,'marker'=>$marker,'tokenSha256'=>$tokenHash]);
        $this->writePrivate('data/opentour-control-writer.json',(object)['contactId'=>$contactId,'token'=>$input->token]);
        $io->writeLine(json_encode(['contactId'=>$contactId,'writerReference'=>'data/opentour-control-writer.json','bootstrapped'=>true],JSON_THROW_ON_ERROR));
    }
}
