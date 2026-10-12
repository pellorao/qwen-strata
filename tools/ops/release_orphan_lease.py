"""Finish the release of a lease whose run died (crash, killed driver), from the key file it left behind.

    python3 -m tools.ops.release_orphan_lease <folder holding controller-key.private.json>

Stops the model, returns the key and deletes the key file; the key is never printed.  If the frontend no longer
accepts that key (someone else holds the lease now, or it was already released), nothing is touched: it reports and
exits with status 1, never taking a lease over.
"""
import argparse
import sys
import urllib.error

from tools.ops.controller_client import Controller


def release(folder, log=print):
    owner = Controller.resume(folder)
    try:
        status = owner.call('/model/status')['status']
    except urllib.error.HTTPError as error:
        if error.code != 403:
            raise
        owner.key = None  # not the holder: never release or stop on its behalf
        log(f'The frontend refuses the key in {folder}; it no longer holds the lease. Nothing changed.')
        return False
    log(f'Model status: {status}')
    if status != 'stopped':
        log(f'Model stop: {owner.stop().get("status")}')
    owner.__exit__(None, None, None)  # releases the lease and deletes the key file
    log('Lease returned, key file deleted.')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folder')
    sys.exit(0 if release(parser.parse_args().folder) else 1)


if __name__ == '__main__':
    main()
