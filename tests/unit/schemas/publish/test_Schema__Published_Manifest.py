from sgit_ai.safe_types.Enum__Published_Layout           import Enum__Published_Layout
from sgit_ai.safe_types.Enum__Visibility                 import Enum__Visibility
from sgit_ai.schemas.publish.Schema__Plaintext_Entry     import Schema__Plaintext_Entry
from sgit_ai.schemas.publish.Schema__Published_Manifest  import (PUBLISHED_SCHEMA_VERSION,
                                                                 Schema__Published_Manifest)
from sgit_ai.schemas.publish.Schema__Published_Object    import Schema__Published_Object


class Test_Schema__Published_Manifest:

    def _manifest(self):
        manifest = Schema__Published_Manifest(
            schema       = PUBLISHED_SCHEMA_VERSION,
            vault_id     = 'q7r6d5zd',
            generated_by = 'sgit v0.15.6',
            layout       = Enum__Published_Layout.API_PATH,
            visibility   = Enum__Visibility.PUBLIC,
            head         = 'obj-cas-imm-aabbccddeeff')
        manifest.objects.append(Schema__Published_Object(
            file_id='bare/refs/ref-pid-muw-1995ccf51fe8', size=69, sha256='a' * 64))
        manifest.plaintext_surface.append(Schema__Plaintext_Entry(path='index.html', sha256='b' * 64))
        manifest.plaintext_surface.append(Schema__Plaintext_Entry(path='manifest.json', sha256=None))
        manifest.commits.append('obj-cas-imm-aabbccddeeff')
        return manifest

    def test_round_trip(self):
        manifest = self._manifest()
        as_json  = manifest.json()
        assert Schema__Published_Manifest.from_json(as_json).json() == as_json

    def test_schema_version_literal(self):
        assert PUBLISHED_SCHEMA_VERSION == 'sgit_published_v1'
        assert str(self._manifest().schema) == 'sgit_published_v1'

    def test_enums_serialise_to_wire_values(self):
        as_json = self._manifest().json()
        assert as_json['layout']     == 'api-path'
        assert as_json['visibility'] == 'public'


class Test_Schema__Published_Object:

    def test_round_trip(self):
        entry = Schema__Published_Object(file_id='bare/data/obj-cas-imm-4ccb5bc28ba1',
                                         size=8871, sha256='c' * 64)
        assert Schema__Published_Object.from_json(entry.json()).json() == entry.json()


class Test_Schema__Plaintext_Entry:

    def test_round_trip_with_and_without_hash(self):
        with_hash = Schema__Plaintext_Entry(path='cover.json', sha256='d' * 64)
        assert Schema__Plaintext_Entry.from_json(with_hash.json()).json() == with_hash.json()
        no_hash = Schema__Plaintext_Entry(path='manifest.json', sha256=None)
        assert Schema__Plaintext_Entry.from_json(no_hash.json()).json() == no_hash.json()
