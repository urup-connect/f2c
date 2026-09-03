"""Fail a deployment job naming the GitHub variables it needs and does not have.

Usage, from a job that has checked the repository out::

    - name: Check the deployment variables
      env:
        VARS: ${{ toJSON(vars) }}
        ENVIRONMENT: qa
      run: python3 .github/scripts/require_vars.py AZURE_CLIENT_ID ACR_NAME

**This exists because the failure it replaces names nothing.** With the three
Azure variables unset, ``azure/login`` answers::

    Login failed with Error: Using auth-type: SERVICE_PRINCIPAL. Not all values
    are present. Ensure 'client-id' and 'tenant-id' are supplied.. Double check
    if the 'auth-type' is correct

-- which sends whoever reads it to the action's inputs and its ``auth-type``,
while the actual fault is a GitHub environment with nothing set on it. Every
variable further down a job fails worse rather than better: an empty
``ACR_NAME`` becomes ``az acr login --name ''``, an empty ``CONTAINERAPP_API``
becomes a container app that does not exist, and an empty ``AZURE_RESOURCE_GROUP``
becomes an ``az containerapp update`` against a group nobody named. Different
messages about the same class of fault, none of them naming which variable or
where it is set.

So each job states the variables it reads and they are checked once, before the
first of them is used. Same argument as ``frontend/deploy/entrypoint.sh``, which
does this for the frontend containers' own settings: fail on the name the
operator has to set, before anything that needs it runs.

**``vars`` and not ``secrets``, which is the mistake to expect.** Azure's own
documentation uses ``secrets.AZURE_CLIENT_ID``; every workflow here reads
``vars.``, deliberately -- ``azure-oidc-setup.sh`` carries the reason, which is
that none of the three is usable without the federated trust and a job running
in this repository under this environment. A client ID added under Settings >
Secrets leaves ``vars.AZURE_CLIENT_ID`` empty and produces exactly the login
failure above, so the message below says so.

**Python rather than another bash script, and JSON rather than one environment
variable per name.** ``ci.yml`` already runs its guards this way -- the MySQL
wait and the ``connection.vendor`` assertion are both inline Python -- and it
needs no ``jq``, which nothing else in this repository depends on. The whole
``vars`` context arrives as JSON so that a job adding a variable to its list
does not also have to map it into the step's environment; GitHub merges
repository and environment variables before serialising it, so what is checked
is what the job would actually read.
"""
import json
import os
import sys

SETUP_SCRIPT = './.github/scripts/azure-oidc-setup.sh'


def missing_names(names, values):
    """The names with no usable value, in the order they were asked for.

    Whitespace counts as unset: a variable set to a space is one somebody meant
    to set and did not, and every consumer downstream treats it as empty.

    A non-string value is possible -- a variable is always a string coming from
    GitHub, but a caller passing its own mapping is not bound by that -- so it
    is stringified rather than assumed.
    """
    return [name for name in names if not str(values.get(name, '')).strip()]


def report(names, environment):
    """The whole message, as a string. Pure, so the wording is testable."""
    where = f'the {environment!r} environment' if environment else 'this repository'

    return '\n'.join(
        [
            f'Not set as GitHub Actions variables on {where}:',
            '',
            *(f'  {name}' for name in names),
            '',
            'Variables, not secrets: every workflow here reads ${{ vars.NAME }},',
            'so a value added under Settings > Secrets reads as empty.',
            '',
            'The four AZURE_* and ACR_NAME are set for you by:',
            '',
            f'    ENVIRONMENT={environment or "qa"} ACR_NAME=... RESOURCE_GROUP=... \\',
            f'        {SETUP_SCRIPT}',
            '',
            'That script also prints the rest, which only you can supply -- the',
            'container app names and the frontend build arguments.',
        ]
    )


def main(argv):
    names = argv[1:]
    if not names:
        print('require_vars.py: name at least one variable', file=sys.stderr)
        return 2

    raw = os.environ.get('VARS')
    if not raw:
        print(
            "require_vars.py: VARS is empty. Pass ${{ toJSON(vars) }} in the "
            "step's env.",
            file=sys.stderr,
        )
        return 2

    values = json.loads(raw)
    absent = missing_names(names, values)

    if absent:
        print(report(absent, os.environ.get('ENVIRONMENT', '').strip()), file=sys.stderr)
        return 1

    environment = os.environ.get('ENVIRONMENT', '').strip()
    where = f'the {environment!r} environment' if environment else 'this repository'
    print(f'All {len(names)} deployment variables are set on {where}.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
