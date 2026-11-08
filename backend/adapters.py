"""Bounded GET-only adapters. No imports, owner CSV access or native mutations."""
from __future__ import annotations

import json
import re
import stat
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class Failure(Exception):
    def __init__(self, code, status=502):
        self.code, self.status = code, status
        super().__init__(code)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def private_json(path):
    path = Path(path)
    if not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise Failure('private_config_unavailable', 503)
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise Failure('private_config_invalid', 503) from None


class JsonGET:
    def __init__(self, base, headers=None):
        url = urllib.parse.urlsplit(base)
        if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.username or url.password or url.query or url.fragment:
            raise Failure('upstream_must_be_local_loopback', 503)
        self.base, self.headers = base.rstrip('/'), headers or {}
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def get(self, path, params=None):
        if not path.startswith('/') or path.startswith('//') or '..' in path.split('/'):
            raise Failure('invalid_upstream_path', 400)
        url = self.base + path
        if params:
            url += '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=self.headers, method='GET')
        try:
            with self.opener.open(req, timeout=6) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise Failure('upstream_response_too_large')
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise Failure('source_object_not_found', 404) from None
            if exc.code in (401, 403):
                raise Failure('source_access_unavailable', 503) from None
            raise Failure('source_http_error') from None
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            raise Failure('source_unavailable', 503) from None


CRM_FIELDS = 'id,name,firstName,lastName,emailAddress,phoneNumber,description,modifiedAt,createdAt'


class EspoCRM:
    """credential_file: private JSON {apiKey: ...}; never passed to the browser."""
    def __init__(self, base='http://127.0.0.1:18082', credential_file=None):
        self.base, self.credential_file = base, credential_file

    def _client(self):
        if not self.credential_file:
            raise Failure('crm_read_credential_not_configured', 503)
        config = private_json(self.credential_file)
        key = config.get('apiKey')
        if not isinstance(key, str) or not key.strip():
            raise Failure('crm_read_credential_invalid', 503)
        return JsonGET(self.base + '/api/v1', {'X-Api-Key': key})

    def list(self, entity, *, offset, limit, query, has_email, has_phone):
        where = []
        if query:
            where.append({'type': 'or', 'value': [
                {'type': 'contains', 'attribute': field, 'value': query}
                for field in ('name', 'emailAddress', 'phoneNumber')]})
        for flag, field in ((has_email, 'emailAddress'), (has_phone, 'phoneNumber')):
            if flag is not None:
                where.append({'type': 'isNotNull' if flag else 'isNull', 'attribute': field})
        select = CRM_FIELDS if entity == 'Contact' else 'id,name,type,emailAddress,phoneNumber,modifiedAt,createdAt'
        search = {
            'offset': offset, 'maxSize': limit, 'select': select,
            'orderBy': 'id', 'order': 'ASC', 'where': where}
        # Espo's multi-param parser discards a string `where`. The JSON search
        # envelope requires typed select arrays and numeric paging values.
        search['select'] = select.split(',')
        result = self._client().get('/' + entity, {'searchParams': json.dumps(search)})
        if not isinstance(result, dict) or not isinstance(result.get('list'), list) or type(result.get('total')) is not int or result['total'] < 0:
            raise Failure('crm_list_contract_invalid')
        if len(result['list']) != min(limit, max(0, result['total'] - offset)):
            raise Failure('crm_list_contract_invalid')
        return result

    def detail(self, entity, key):
        obj = self._client().get('/' + entity + '/' + urllib.parse.quote(key, safe=''))
        if not isinstance(obj, dict) or obj.get('id') != key or obj.get('deleted'):
            raise Failure('source_object_not_found', 404)
        return obj


class NativeWork:
    def __init__(self, work_root, mission, project='opentour', rig='opentour-rig', base='http://127.0.0.1:7433'):
        self.root = Path(work_root).resolve()
        self.mission, self.project, self.rig = mission, project, rig
        self.client = JsonGET(base)

    def snapshot(self):
        # The installed /api/slices list ignores ?project in this version.
        # Enumerate through the explicitly scoped native CLI; never use that global list.
        try:
            result = subprocess.run([
                'rig', 'scope', '--workspace', str(self.root), 'slice', 'ls',
                '--mission', self.mission, '--json'], capture_output=True, timeout=12, check=True)
            if len(result.stdout) > 1024 * 1024:
                raise Failure('native_catalog_too_large')
            catalog = json.loads(result.stdout)
        except (subprocess.SubprocessError, OSError, ValueError):
            raise Failure('native_catalog_unavailable', 503) from None
        if not isinstance(catalog, dict) or catalog.get('ok') is not True or not isinstance(catalog.get('slices'), list):
            raise Failure('native_catalog_invalid')
        summaries = catalog['slices']
        if len(summaries) > 100:
            raise Failure('native_catalog_too_large')
        queue = self.client.get('/api/queue/list', {'rig': self.rig, 'limit': 1000, 'compact': 1})
        if not isinstance(queue, list):
            raise Failure('native_queue_invalid')
        queue_complete = len(queue) < 1000
        queue = [q for q in queue if isinstance(q, dict)
                 and 'project:' + self.project in (q.get('tags') or [])
                 and 'mission:' + self.mission in (q.get('tags') or [])]
        slices = []
        expected = self.root / 'missions' / self.mission / 'slices'
        for summary in summaries:
            name = summary.get('name', '')
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', name) or summary.get('mission') != self.mission:
                raise Failure('native_catalog_scope_mismatch')
            path = Path(summary.get('path', '')).resolve()
            if path != expected / name or not path.is_dir():
                raise Failure('native_catalog_scope_mismatch')
            detail = self.client.get('/api/slices/' + name, {'project': self.project, 'mission': self.mission})
            if (detail.get('name') != name or detail.get('missionId') != self.mission
                    or Path(detail.get('slicePath', '')).resolve() != path):
                raise Failure('native_detail_scope_mismatch')
            # Only authored safe progress material, never terminal/story/body fields.
            progress_path = path / 'PROGRESS.md'
            if progress_path.resolve().parent != path or not progress_path.is_file():
                raise Failure('native_progress_unavailable')
            text = progress_path.read_text(encoding='utf-8')
            if len(text) > 256000:
                raise Failure('native_progress_too_large')
            outcomes = re.search(r'^## Outcomes\s*\n(.*?)(?=^## |\Z)', text, re.S | re.M)
            bullets = re.findall(r'^- (.+)$', outcomes.group(1), re.M) if outcomes else []
            current = re.search(r'^## Current state\s*\n(.*?)(?=^## |\Z)', text, re.S | re.M)
            slices.append({
                'name': name, 'sourceId': summary.get('id') or name,
                'title': detail.get('displayName') or name,
                'authoredStatus': summary.get('status'),
                'nativeStatus': detail.get('status'), 'readiness': detail.get('readiness', {}).get('state'),
                'lastActivityAt': detail.get('lastActivityAt'),
                'lastResult': bullets[-1] if bullets else None,
                'currentContext': current.group(1).strip() if current else None,
                'queue': [q for q in queue if 'slice:' + name in (q.get('tags') or [])]})
        return slices, queue_complete
