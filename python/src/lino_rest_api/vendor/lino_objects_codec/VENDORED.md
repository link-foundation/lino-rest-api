# Vendored `lino-objects-codec`

These files are a verbatim copy of the Python implementation of
[`lino-objects-codec`](https://github.com/link-foundation/lino-objects-codec). The codec is published
to npm and crates.io but not to PyPI, so the Python package carries the sources
instead of depending on a release.

- Upstream: https://github.com/link-foundation/lino-objects-codec
- Commit: `8642bfbf907cb0b7125718ee0e0b26dbf13e94ba`
- Synchronised by: `node scripts/sync-vendored-codec.mjs`

Do not edit these files. Run the script to update them, and
`node scripts/sync-vendored-codec.mjs --check` to verify that the copy still
matches the pinned commit. `python/tests/test_codec_parity.py` proves the copy
encodes the shared fixtures exactly as the npm package does.

| File | SHA-256 |
| ---- | ------- |
| `python/src/lino_rest_api/vendor/lino_objects_codec/__init__.py` | `e5bc1e02b3720e2538f6e1b0b4fd7a4cb8696c27082a2aca6a900a5ff42e9a03` |
| `python/src/lino_rest_api/vendor/lino_objects_codec/debug.py` | `5b58a15724421d2e9c8d65a0887a45afc67055e6f14a0a679010d32fd26490e9` |
| `python/src/lino_rest_api/vendor/lino_objects_codec/format.py` | `bd863a1d5dda4140b89b9fe07940fe111d213652ab72dfce603874b3dce03937` |
| `python/src/lino_rest_api/vendor/lino_objects_codec/readable.py` | `0dc17c527a0dc7b76df2084e99b3fa557cd63b70c696eb53396020e6802fade8` |
| `python/src/lino_rest_api/vendor/lino_objects_codec/codec.py` | `b5096a77130caf75305eac3d02136a6b74443efe3f3a3f87ba1825c67cf5a569` |
| `python/tests/fixtures/readable-format-cases.json` | `8fa38242996933e7e87817bd1c44f2f1b3ae133b7fdd9670c7a38d1db6bfb895` |
