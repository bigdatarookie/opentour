"""Read-only projection of the existing, immutable r01 FIXTURE package. No provider/recipients."""
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re

from .adapters import Failure

CAMPAIGN_ID = 'fixture:campaign:draft-r01'
ARTIFACTS = Path(__file__).resolve().parents[1] / 'opentour-rig/missions/01-local-information-layer/slices/04-campaign-draft/artifacts'
FILES = {
    'draft-r01.md': 'dba35fdb4f1e1243f6fc6064e9dc5d457df8df4eae041540ac14a37ab9129f6a',
    'email-preview-r01.html': 'b29e27e535a316b1ccdf55d730e4c34246cf6a5d14000041c9791dcfe2754b95',
    'email-preview-r01.txt': '01cccff52686c05e105dac1c26425f250b1a2d4420257c53aaf9ff7246c6e513',
    'offer-r01.md': '528c381ae09c60d52ccf8681fed86c23b55dc3702733bba56f9170a59501d354',
    'email-r01.md': '374d4817c7be40da033dc02f7ea7d3da16852b3b29ffd8830c56c968036f1216'}
LABELS = ['FIXTURE', 'PREVIEW-ONLY', 'NOT CONTENT-APPROVED', 'NOT SENT']
SOURCES = [
    {'title': '«Дельфин» · акция 5443', 'url': 'https://www.delfin-tour.ru/promo/5443.html'},
    {'title': 'Программа тура «Кольцо Байкала»', 'url': 'https://www.delfin-tour.ru/tours/24676.html'}]


class InertSourceCheck(HTMLParser):
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'iframe', 'object', 'embed', 'img', 'svg', 'form', 'input', 'link', 'video', 'audio', 'base'):
            raise Failure('campaign_fixture_unsafe', 503)
        if any(key.startswith('on') or key in ('src', 'srcset', 'action', 'formaction', 'style') for key, _ in attrs):
            raise Failure('campaign_fixture_unsafe', 503)
        if tag == 'button' and 'disabled' not in dict(attrs):
            raise Failure('campaign_fixture_unsafe', 503)
        if tag == 'a' and dict(attrs).get('href') not in {source['url'] for source in SOURCES}:
            raise Failure('campaign_fixture_unsafe', 503)


class FixtureCampaign:
    def __init__(self, root=ARTIFACTS):
        self.root = Path(root)

    def _files(self):
        documents = {}
        try:
            root = self.root.resolve(strict=True)
            for name, expected in FILES.items():
                path = root / name
                if path.resolve(strict=True).parent != root or path.stat().st_size > 65536:
                    raise Failure('campaign_fixture_invalid', 503)
                data = path.read_bytes()
                if hashlib.sha256(data).hexdigest() != expected:
                    raise Failure('campaign_fixture_revision_mismatch', 503)
                documents[name] = data.decode('utf-8')
        except (OSError, UnicodeError):
            raise Failure('campaign_fixture_unavailable', 503) from None
        return documents

    def _preview(self, html):
        InertSourceCheck().feed(html)
        styles = re.findall(r'<style>(.*?)</style>', html, re.S)
        if len(styles) != 1 or re.search(r'url\s*\(|@import|expression\s*\(', styles[0], re.I):
            raise Failure('campaign_fixture_unsafe', 503)
        # Preserve the known r01 layout using a same-origin stylesheet, without
        # relaxing the application's no-inline-style CSP. Embedded links are inert.
        preview = re.sub(r'<style>.*?</style>', '<link rel="stylesheet" href="/ui/campaign-email.css">', html, flags=re.S)
        preview = re.sub(r'\s+href="https://[^"]+"', '', preview)
        preview = preview.replace('</head>', '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'self\'; img-src \'none\'; form-action \'none\'; base-uri \'none\'">\n</head>')
        return preview, styles[0]

    def detail(self, key=CAMPAIGN_ID):
        if key != CAMPAIGN_ID:
            raise Failure('campaign_not_found', 404)
        files = self._files()
        html, _ = self._preview(files['email-preview-r01.html'])
        subject = next((line.removeprefix('Тема: ').strip() for line in files['email-preview-r01.txt'].splitlines() if line.startswith('Тема: ')), None)
        if not subject:
            raise Failure('campaign_fixture_invalid', 503)
        return {'id': CAMPAIGN_ID, 'title': subject, 'subject': subject, 'channel': 'email',
                'mode': 'FIXTURE', 'labels': LABELS, 'revisions': ['offer-r01', 'email-r01', 'draft-r01'],
                'audience': {'status': 'not_selected', 'count': None}, 'sender': None, 'providerId': None,
                'sourceLinks': SOURCES, 'previewDocument': html, 'plainText': files['email-preview-r01.txt'],
                'manifest': files['draft-r01.md'],
                'materials': [{'name': name, 'sha256': sha} for name, sha in FILES.items()],
                'caveats': [
                    'Цена и условия — по октябрьским снимкам источников, проверенным 8 ноября 2026 года; это не актуальная котировка.',
                    'Наличие, итоговая цена, включения, дополнительные расходы и условия отмены не подтверждены.',
                    'Цена 160 000 RUB на человека применима при 2–3-местном размещении, бронировании и полной оплате до 20 января 2027 года. Оператор может изменить или отменить акцию.',
                    'Изображения не используются; права не проверены. Имя «Олян» не подтверждено.',
                    'Решение оставить r01 для предпросмотра не является одобрением содержания или разрешением отправки.'],
                'version': hashlib.sha256(''.join(FILES.values()).encode()).hexdigest()}

    def list(self):
        detail = self.detail()
        return {'mode': 'FIXTURE', 'items': [{k: detail[k] for k in ('id', 'title', 'subject', 'channel', 'mode', 'labels', 'audience', 'version')}], 'total': 1}

    def stylesheet(self):
        _, css = self._preview(self._files()['email-preview-r01.html'])
        return css.encode()

    def material(self, name):
        if name not in FILES:
            raise Failure('campaign_material_not_found', 404)
        return {'mode': 'FIXTURE', 'name': name, 'content': self._files()[name], 'sha256': FILES[name]}
