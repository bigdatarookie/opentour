<?php
namespace Espo\Modules\OpenTourControl\Services;

use Espo\Core\Utils\Metadata;
use Espo\Core\Exceptions\Forbidden;

/** Fixed native business field; never a caller-selected ORM attribute. */
class FirstNameControl extends TitleControl
{
    public const FIELD = 'firstName';
    protected const VALUE_KEY = 'firstName';

    public static function requireStorage(Metadata $metadata): void
    {
        $path=['entityDefs','Contact','fields',self::FIELD];
        if ($metadata->get([...$path,'type'])!=='varchar' || $metadata->get([...$path,'maxLength'])!==100
            || $metadata->get([...$path,'notStorable'])===true || $metadata->get([...$path,'select'])!==null) {
            throw new Forbidden('native_first_name_storage_unavailable');
        }
    }

    protected static function validValue($value): bool
    {
        return is_string($value) && trim($value)!=='';
    }
}
