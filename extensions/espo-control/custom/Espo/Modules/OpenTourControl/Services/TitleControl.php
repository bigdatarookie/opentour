<?php
namespace Espo\Modules\OpenTourControl\Services;

use Espo\Core\ORM\EntityManager;
use Espo\Core\Exceptions\{BadRequest,Forbidden,Conflict,NotFound};

/** A capability for one synthetic Contact.title, not an Espo API-user credential. */
class TitleControl
{
    public function __construct(private EntityManager $em) {}

    public static function privateJson(string $file): object
    {
        if (is_link($file) || !is_file($file) || (fileperms($file)&0077) || fileowner($file)!==posix_geteuid()) {
            throw new Forbidden('control_config_unavailable');
        }
        $data=json_decode(file_get_contents($file), false, 16, JSON_THROW_ON_ERROR);
        if (!is_object($data)) throw new Forbidden('control_config_invalid');
        return $data;
    }

    public static function exact(object $data, array $keys): void
    {
        if (array_diff(array_keys(get_object_vars($data)), $keys) || array_diff($keys, array_keys(get_object_vars($data)))) {
            throw new BadRequest('control_fields_forbidden');
        }
    }

    public function authorize(string $token): object
    {
        $config=self::privateJson('data/opentour-control.json');
        self::exact($config,['contactId','marker','tokenSha256']);
        if (!is_string($token) || !preg_match('/^[A-Za-z0-9_-]{32,128}$/D',$token)
            || !is_string($config->tokenSha256) || !hash_equals($config->tokenSha256,hash('sha256',$token))
            || !is_string($config->contactId) || !preg_match('/^[A-Za-z0-9]{17,24}$/D',$config->contactId)
            || !is_string($config->marker) || !preg_match('/^opentour-synthetic-control:[a-f0-9]{64}$/D',$config->marker)) {
            throw new Forbidden('control_capability_forbidden');
        }
        return $config;
    }

    private function snapshot($contact): array
    {
        $data=['entity'=>'Contact','id'=>$contact->getId(),'title'=>$contact->get('title') ?? ''];
        $data['version']=hash('sha256',json_encode([$data['id'],$data['title'],$contact->get('modifiedAt')],JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR));
        return $data;
    }

    private function contact(object $config, bool $lock=false)
    {
        $query=$this->em->getRDBRepository('Contact')->where(['id'=>$config->contactId,'deleted'=>false]);
        if ($lock) $query=$query->forUpdate();
        $contact=$query->findOne();
        if (!$contact || $contact->get('description')!==$config->marker) throw new Forbidden('control_record_not_pinned');
        return $contact;
    }

    private function receiptId(string $operation): string
    {
        return substr(hash('sha256','OpenTourControlTitle:'.$operation),0,17);
    }

    private function receipt(string $operation): ?object
    {
        $row=$this->em->getEntityById('UniqueId',$this->receiptId($operation));
        if (!$row) return null;
        if ($row->get('name')!=='OpenTourControlTitle:'.$operation) throw new Conflict('control_receipt_collision');
        return $row->get('data');
    }

    public function read(object $config): array { return $this->snapshot($this->contact($config)); }

    public function status(object $config, string $operation): array
    {
        if (!preg_match('/^[a-f0-9]{64}$/D',$operation)) throw new BadRequest('control_operation_invalid');
        $data=$this->receipt($operation);
        if (!$data || ($data->result->id ?? null)!==$config->contactId) throw new NotFound('control_operation_not_found');
        return (array)$data->result;
    }

    public function edit(object $config, object $body): array
    {
        self::exact($body,['operationId','title','baseVersion','actor']);
        if (!is_string($body->operationId) || !preg_match('/^[a-f0-9]{64}$/D',$body->operationId)
            || !is_string($body->title) || mb_strlen($body->title)>100 || preg_match('/[\x00-\x1f\x7f]/u',$body->title)
            || !is_string($body->baseVersion) || !preg_match('/^[a-f0-9]{64}$/D',$body->baseVersion)
            || !is_string($body->actor) || $body->actor==='' || mb_strlen($body->actor)>128) {
            throw new BadRequest('control_value_invalid');
        }
        $digest=hash('sha256',json_encode([$config->contactId,$body->title,$body->baseVersion,$body->actor],JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR));
        return $this->em->getTransactionManager()->run(function() use($config,$body,$digest) {
            $contact=$this->contact($config,true); // Serialize CAS + same-operation receipt on this exact row.
            $existing=$this->receipt($body->operationId);
            if ($existing) {
                if (($existing->digest ?? null)!==$digest) throw new Conflict('control_operation_conflict');
                return (array)$existing->result;
            }
            if ($this->snapshot($contact)['version']!==$body->baseVersion) throw new Conflict('control_version_conflict');
            $contact->set('title',$body->title); // No generic entity, ID or field from the caller.
            $this->em->saveEntity($contact,['skipHooks'=>true]); // Synthetic control: suppress unrelated business hooks; normal audit timestamps remain.
            $result=$this->snapshot($contact)+['operationId'=>$body->operationId,'saved'=>true,'baseVersion'=>$body->baseVersion,'actor'=>$body->actor];
            $receipt=$this->em->getNewEntity('UniqueId');
            $receipt->set('id',$this->receiptId($body->operationId));
            $receipt->set('name','OpenTourControlTitle:'.$body->operationId);
            $receipt->set('data',(object)['digest'=>$digest,'result'=>(object)$result]);
            // Null terminateAt keeps the existing system receipt until explicit safe cleanup.
            $this->em->saveEntity($receipt);
            return $result;
        });
    }
}
