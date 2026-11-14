<?php
namespace Espo\Modules\OpenTourControl\Api;

use Espo\Modules\OpenTourControl\Services\FirstNameControl;

class FirstName extends Title
{
    public function __construct(FirstNameControl $control) {parent::__construct($control);}
}
