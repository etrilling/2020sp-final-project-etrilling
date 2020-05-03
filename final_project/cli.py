import argparse
import os
from luigi.contrib.s3 import S3Client, FileNotFoundException

from .luigi_tasks import DownloadAllLectures, UploadAllLectures
from luigi import build


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
        # if we are doing an upload, make sure the S3_ROOT pulled from the .env file exists and is viable
        if os.getenv('S3_ROOT') is None:
            raise KeyError('DEBUG: you must set an S3_ROOT variable')
        else:
            root = os.getenv('S3_ROOT')
            if S3Client().is_dir(root) is False:
                raise FileNotFoundException(f'S3_ROOT ({root}) is not a valid directory')
        
        # run the task
        build([UploadAllLectures(**params)], local_scheduler=True)
    
    
    print('*'*100 + '\n' + '*'*100)
    print('THE PROGRAM HAS FINISHED RUNNING!')
    print('*'*100 + '\n' + '*'*100)
