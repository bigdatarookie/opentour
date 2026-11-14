<?php
namespace Espo\Modules\OpenTourControl\Api;
use Espo\Core\Api\{Action,Request,Response,ResponseComposer};
use Espo\Core\Exceptions\{Forbidden,BadRequest};
use Espo\Modules\OpenTourControl\Services\TitleControl;

class Title implements Action
{
    public function __construct(private TitleControl $control) {}
    public function process(Request $request): Response
    {
        // noAuth routes use a purpose-specific capability, never a native API identity.
        foreach (['Authorization','Espo-Authorization','X-Api-Key','X-Hmac-Authorization'] as $header) {
            if ($request->hasHeader($header)) throw new Forbidden('native_auth_not_accepted');
        }
        if (count($request->getHeaderAsArray('X-OpenTour-Control'))!==1 || $request->getQueryParams()) {
            throw new Forbidden('control_request_forbidden');
        }
        $config=$this->control->authorize($request->getHeader('X-OpenTour-Control') ?? '');
        $operation=$request->getRouteParam('operationId');
        if ($request->getMethod()==='GET') {
            $data=$operation!==null ? $this->control->status($config,$operation) : $this->control->read($config);
        } elseif ($request->getMethod()==='POST' && $operation===null) {
            if ($request->getHeader('Content-Type')!=='application/json' || strlen($request->getBodyContents() ?? '')>2048) throw new BadRequest('control_json_required');
            $data=$this->control->edit($config,$request->getParsedBody());
        } else throw new Forbidden('control_method_forbidden');
        return ResponseComposer::json($data)->setHeader('Cache-Control','no-store');
    }
}
