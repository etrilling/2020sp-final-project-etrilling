from .luigi_tasks import DownloadAllLectures, UploadAllLectures
import argparse


parser = argparse.ArgumentParser(description='TODO?! Command description.', allow_abbrev=False)
parser.add_argument('action', choices=['download', 'upload'], help='TODO')
parser.add_argument('target_url', help='TODO')
parser.add_argument('--full', help='TODO', action='store_true')
parser.add_argument('--process_slides', help='TODO', action='store_true')


def main():
    args = parser.parse_args()
    
    params = {'master_URL': args.target_url,
              'process_slides': args.process_slides,
              'is_test_run': not args.full}
    
    if args.action == 'download':
        build([DownloadAllLectures(**params)], local_scheduler=True)
    elif args.action == 'upload':
        build([UploadAllLectures(**params)], local_scheduler=True)
    
    print('done!')
