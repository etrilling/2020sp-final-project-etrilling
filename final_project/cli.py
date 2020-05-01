from .luigi_tasks import DownloadAllLectures, UploadAllLectures
import argparse


parser = argparse.ArgumentParser(allow_abbrev=False)
parser.add_argument('command', choices=['download', 'upload'], help='action to take')
parser.add_argument('target_url', help='Canvas URL to download from')
parser.add_argument('--full', help='do a full run (not a just a test run)', action='store_true')
parser.add_argument('--process_slides', help='download slides (only effects Panopto player)', action='store_true')


def main():
    args = parser.parse_args()
    
    params = {'master_URL': args.target_url,
              'process_slides': args.process_slides,
              'is_test_run': not args.full}
    
    if args.command == 'download':
        build([DownloadAllLectures(**params)], local_scheduler=True)
    elif args.command == 'upload':
        build([UploadAllLectures(**params)], local_scheduler=True)
    
    print('done!')
