"""Generate the three secrets an environment needs, ready to paste into a `.env`.

    python design/tools/generate_keys.py            # all three, .env format
    python design/tools/generate_keys.py --field    # one value, bare
    python design/tools/generate_keys.py --self-test # prove the generator, print no secret

Standard library only and no Django import, so it runs against any Python on any
machine -- including one that has never had this project's dependencies
installed. That matters because these are generated once, by whoever is standing
an environment up, and that is not always a developer at a working checkout.

**Every value printed is a secret.** Nothing here writes to a file: a generator
that appends to `.env` is one that eventually appends to the wrong `.env`, and
the failure is silent until something cannot decrypt. Paste them where they go --
see `design/deploy.md` section 3 for which store each belongs in.

The two 32-byte keys are checked against `app/core/common/crypto._decode_key`,
which is the only thing that reads them: URL-safe base64, decoding to exactly 32
bytes. The check is repeated here rather than imported so this file stays
dependency-free, and `--self-test` is what keeps the duplicate honest.
"""

import argparse
import base64
import secrets
import sys

# Both keys are read by `_decode_key(raw, name, 32)`. AES-GCM takes a 256-bit
# key and the blind index is an HMAC keyed with the same width -- there is no
# reason for them to differ and one fewer number to get wrong if they do not.
KEY_BYTES = 32

# Django's own `get_random_secret_key` draws 50 characters from a 50-character
# alphabet, which is about 282 bits. `token_urlsafe(64)` is 512, costs nothing,
# and avoids importing Django to get it.
SECRET_KEY_BYTES = 64


def generate_key():
    """A 32-byte secret, URL-safe base64, in the form the settings expect."""
    return base64.urlsafe_b64encode(secrets.token_bytes(KEY_BYTES)).decode()


def generate_secret_key():
    """A value for ``DJANGO_SECRET_KEY``.

    No format requirement beyond being long and unguessable -- Django signs with
    it, nothing decodes it, so unlike the two above it can be rotated whenever
    without touching stored data. Rotating it only invalidates live sessions and
    any unused signed token.
    """
    return secrets.token_urlsafe(SECRET_KEY_BYTES)


def valid(value):
    """Whether ``value`` would survive ``crypto._decode_key``.

    The same three conditions in the same order, so a failure here is a failure
    there: present, decodable as URL-safe base64, exactly 32 bytes decoded.
    """
    if not value:
        return False
    try:
        decoded = base64.urlsafe_b64decode(value)
    except (ValueError, TypeError):
        return False
    return len(decoded) == KEY_BYTES


def self_test():
    """Prove the generator without printing anything anybody could use.

    Exists so this file can be run on the machine that will hold the real keys,
    to check the Python there behaves, without putting a usable secret into a
    terminal history or a screenshot.
    """
    failures = []

    for _ in range(100):
        key = generate_key()
        if not valid(key):
            failures.append(f'generated a key that would be refused: {len(key)} chars')
            break

    if len({generate_key() for _ in range(100)}) != 100:
        failures.append('generated a duplicate key in 100 draws')

    for bad, why in (
        ('', 'empty'),
        ('not base64 at all!!', 'not base64'),
        (base64.urlsafe_b64encode(secrets.token_bytes(16)).decode(), '16 bytes'),
        (base64.urlsafe_b64encode(secrets.token_bytes(64)).decode(), '64 bytes'),
    ):
        if valid(bad):
            failures.append(f'accepted a value that should be refused ({why})')

    if len(generate_secret_key()) < 64:
        failures.append('secret key is shorter than expected')

    for failure in failures:
        print(f'FAIL: {failure}', file=sys.stderr)

    if failures:
        return 1

    print(f'ok: keys are {KEY_BYTES} bytes, URL-safe base64, and unique')
    print('ok: values that crypto._decode_key would refuse are refused here too')
    print('no secret was printed. Run without --self-test to generate real values.')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Generate the secrets an environment needs.',
        epilog='Every value printed is a secret. See design/deploy.md section 3.',
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--field', action='store_true',
        help='print only DJANGO_FIELD_ENCRYPTION_KEY, bare',
    )
    group.add_argument(
        '--pepper', action='store_true',
        help='print only DJANGO_BLIND_INDEX_PEPPER, bare',
    )
    group.add_argument(
        '--secret-key', action='store_true',
        help='print only DJANGO_SECRET_KEY, bare',
    )
    group.add_argument(
        '--self-test', action='store_true',
        help='check the generator and print no secret',
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    # The bare forms exist to be piped -- into `az keyvault secret set --value`,
    # or into a clipboard. They print the value and nothing else for that reason:
    # a label on stdout would end up inside the secret.
    if args.field or args.pepper:
        print(generate_key())
        return 0
    if args.secret_key:
        print(generate_secret_key())
        return 0

    field = generate_key()
    pepper = generate_key()

    # Cheap, and the one failure worth guarding: two draws from `secrets` are
    # not going to collide, but a future edit that generates one and assigns it
    # twice would produce an environment where rotating the pepper silently
    # destroys every encrypted identity number.
    assert field != pepper, 'the two keys must not be the same value'
    assert valid(field) and valid(pepper)

    print('# Generated secrets. Paste into the environment that needs them and')
    print('# do not commit them. design/deploy.md section 3 says where each goes.')
    print()
    print('# Key Vault. Losing this makes every stored identity number')
    print('# unrecoverable -- design/deploy.md R-D2.')
    print(f'DJANGO_FIELD_ENCRYPTION_KEY={field}')
    print()
    print('# Key Vault. Changing this invalidates every stored digest, so the')
    print('# uniqueness checks on ID numbers and addresses would need a rebuild.')
    print(f'DJANGO_BLIND_INDEX_PEPPER={pepper}')
    print()
    print('# Container App secret. Rotatable at any time; rotating it only ends')
    print('# live sessions and unused signed tokens.')
    print(f'DJANGO_SECRET_KEY={generate_secret_key()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
