"""P4b — api/openapi.json + the Swagger docs page (08 §7 acceptance)."""
import json

from sgit_ai.crypto.Vault__Crypto                            import Vault__Crypto
from sgit_ai.core.actions.publish.Vault__Publish__Api_Docs   import Vault__Publish__Api_Docs
from sgit_ai.network.api.Vault__API__In_Memory               import Vault__API__In_Memory
from sgit_ai.network.assets.Swagger_UI__Assets               import SWAGGER_UI_VERSION

OBJECTS = [('bare/data/obj-cas-imm-4ccb5bc28ba1',    8871, 'a' * 64),
           ('bare/indexes/idx-pid-muw-dd6887115f9d', 214,  'b' * 64),
           ('bare/keys/key-rnd-imm-7239f4aa88819106', 1032, 'c' * 64),
           ('bare/refs/ref-pid-muw-1995ccf51fe8',    69,   'd' * 64)]


def _builder():
    api = Vault__API__In_Memory()
    api.setup()
    return Vault__Publish__Api_Docs(crypto=Vault__Crypto(), api=api)


class Test_OpenAPI_Document:

    def _document(self):
        files = _builder().build('ivpijuvg', OBJECTS, mode=None)
        return json.loads(files['api/openapi.json'])

    def test_servers_is_relative(self):
        assert self._document()['servers'] == [{'url': '.'}]

    def test_describes_only_what_the_folder_serves(self):
        document = self._document()
        assert set(document['paths']) == {'/api/vault/read/{vault_id}/{file_id}',
                                          '/manifest.json', '/cover.json'}
        as_text = json.dumps(document)
        assert 'batch'     not in as_text
        assert 'presigned' not in as_text
        for path_item in document['paths'].values():
            assert set(path_item) == {'get'}                     # GET only, no writes

    def test_examples_are_real_file_ids(self):
        params   = self._document()['paths']['/api/vault/read/{vault_id}/{file_id}']['get']['parameters']
        file_id  = next(p for p in params if p['name'] == 'file_id')
        examples = {e['value'] for e in file_id['examples'].values()}
        assert examples == {'bare/refs/ref-pid-muw-1995ccf51fe8',
                            'bare/indexes/idx-pid-muw-dd6887115f9d',
                            'bare/data/obj-cas-imm-4ccb5bc28ba1'}

    def test_vault_id_is_pinned_as_const(self):
        params   = self._document()['paths']['/api/vault/read/{vault_id}/{file_id}']['get']['parameters']
        vault_id = next(p for p in params if p['name'] == 'vault_id')
        assert vault_id['schema']['const'] == 'ivpijuvg'

    def test_openapi_version_is_31(self):
        assert self._document()['openapi'] == '3.1.0'


class Test_Docs_Page_CDN:

    def _page(self):
        files = _builder().build('ivpijuvg', OBJECTS, mode='cdn')
        return files['api/docs/index.html'].decode('utf-8'), files

    def test_the_five_required_attributes(self):
        page, _files = self._page()
        assert f'swagger-ui-dist@{SWAGGER_UI_VERSION}' in page   # 1. exact version pin
        assert page.count('integrity="sha384-') == 2             # 2. SRI on css and js
        assert page.count('crossorigin="anonymous"') == 2        #    …with crossorigin
        assert page.count('referrerpolicy="no-referrer"') == 2   # 3. no-referrer
        assert 'http-equiv="Content-Security-Policy"' in page    # 4. CSP meta is MANDATORY (SP-11)
        assert "connect-src 'self'" in page                      #    …with the exfiltration backstop
        assert 'cdn.jsdelivr.net' in page

    def test_no_floating_tag(self):
        page, _files = self._page()
        assert '@5/'    not in page
        assert '@5"'    not in page
        assert 'latest' not in page

    def test_degradation_names_the_spec_file(self):
        page, _files = self._page()
        assert './openapi.json' in page or '../openapi.json' in page

    def test_standalone_preset_not_emitted(self):
        page, files = self._page()
        assert 'standalone-preset' not in page
        assert not any('standalone' in name for name in files)

    def test_no_inline_script_under_csp(self):
        page, files = self._page()
        assert 'SwaggerUIBundle({' not in page                   # init lives in same-origin init.js
        assert 'api/docs/init.js' in files

    def test_api_docs_implies_api_spec(self):
        _page, files = self._page()
        assert 'api/openapi.json' in files
