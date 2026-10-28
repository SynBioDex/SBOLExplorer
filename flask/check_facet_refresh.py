"""
Checks the facet refresh log against a running Explorer.

Sends a burst of fake SynBioHub submissions to /incrementalupdate, then watches
log.txt for the "Facet refresh" lines. The parts are not in Virtuoso, so every
refresh finds no collection and the parts are retried at 30 s, 150 s and 750 s
after the submission. Expect a few lines per stage, not one per submission.

Usage (Explorer and Elasticsearch running):
    python check_facet_refresh.py --explorer http://localhost:5000/ --submissions 20
"""
import argparse
import datetime
import json
import os
import sys
import time
import urllib.request

ROLE = 'http://identifiers.org/so/SO:0000167'
DNA = 'http://www.biopax.org/release/biopax-level3.owl#DnaRegion'
CD = 'http://sbols.org/v2#ComponentDefinition'
GRAPH = 'https://synbiohub.org/user/facet_check'

REFRESH_MARKER = 'Facet refresh'


def payload_for(subject):
    # Same shape as SynBioHub's PrepareSubmissionJob sends to /incrementalupdate.
    return {
        'partsToRemove': [],
        'partsToAdd': [{
            'subject': subject, 'displayId': subject.rsplit('/', 1)[-1], 'version': '1',
            'name': 'facet check', 'description': '', 'type': CD,
            'role': ROLE, 'sboltype': DNA, 'graph': GRAPH,
        }],
    }


def post(url, body):
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode()


def file_size(path):
    try:
        return os.path.getsize(path)
    except FileNotFoundError:
        return 0


def read_from(path, offset):
    with open(path, 'rb') as f:
        f.seek(offset)
        return f.read().decode(errors='replace')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--explorer', default='http://localhost:5000/')
    parser.add_argument('--log', default='log.txt', help='general log written by the Explorer')
    parser.add_argument('--indexing-log', default='indexing_log.txt')
    parser.add_argument('--submissions', type=int, default=20)
    parser.add_argument('--spacing', type=float, default=1.0, help='seconds between submissions')
    parser.add_argument('--wait', type=int, default=800, help='seconds to watch the log after the last submission')
    parser.add_argument('--keep', action='store_true', help='do not remove the fake parts from the index at the end')
    args = parser.parse_args()

    explorer = args.explorer.rstrip('/') + '/'
    stamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    subjects = [f'{GRAPH}/facet_{stamp}_{i}/1' for i in range(args.submissions)]

    log_offset = file_size(args.log)
    indexing_offset = file_size(args.indexing_log)

    print(f'Sending {len(subjects)} submissions, {args.spacing}s apart')
    for subject in subjects:
        print(post(explorer + 'incrementalupdate', payload_for(subject)))
        time.sleep(args.spacing)
    sent_at = time.monotonic()

    print(f'Watching {args.log} for {args.wait}s after the last submission')
    seen = ''
    while time.monotonic() - sent_at < args.wait:
        time.sleep(10)
        seen = read_from(args.log, log_offset)

    refresh_lines = [line for line in seen.splitlines() if REFRESH_MARKER in line]
    print('\nFacet refresh lines in general log:')
    for line in refresh_lines:
        print('  ' + line)
    print(f'  total: {len(refresh_lines)} (expected a few per stage: 30 s, 150 s, 750 s, not {len(subjects)} per stage)')

    indexing_new = read_from(args.indexing_log, indexing_offset)
    stray = [line for line in indexing_new.splitlines() if REFRESH_MARKER in line]
    print(f'Facet refresh lines in indexing log: {len(stray)} (expected 0)')

    if not args.keep:
        # Removal relies on delete_subject; if the fake parts stay in the index,
        # the delete bug described in indexing-fixes-writeup.md is still present.
        print(post(explorer + 'incrementalupdate', {'partsToRemove': subjects, 'partsToAdd': []}))
    return 0 if not stray else 1


if __name__ == '__main__':
    sys.exit(main())
