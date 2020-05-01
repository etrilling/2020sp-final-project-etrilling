import os
import re

DATA_PATH = os.path.abspath('./data')

# set VIDEO_PATH
if os.getenv('VIDEO_PATH') is None:
    VIDEO_PATH = os.path.join(DATA_PATH, 'videos')
else:
    VIDEO_PATH = os.getenv('VIDEO_PATH')
    if os.path.isdir(VIDEO_PATH) is False:
        raise OSError(f'VIDEO_PATH ({VIDEO_PATH}) is not a valid directory')


def clean_file_name(file_name):
    '''
    replace all invalid filename characters
    '''
    return re.sub(r'[\\/:*?"<>|]', '_', file_name)
