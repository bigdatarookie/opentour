<?php
namespace Espo\Modules\OpenTourControl\Record\Output;

use Espo\Core\Record\Output\Filter;
use Espo\ORM\Entity;
use Espo\Modules\OpenTourControl\Services\TitleControl;

/** Generic CRM output must never disclose the capability-owned control value. */
final class ControlField implements Filter
{
    public function filter(Entity $entity): void
    {
        if ($entity->getEntityType() === 'Contact') {
            $entity->clear(TitleControl::FIELD);
        }
    }
}
