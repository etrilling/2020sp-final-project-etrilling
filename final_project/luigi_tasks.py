from luigi import Task, Parameter, BoolParameter, IntParameter, build
from luigi.local_target import LocalTarget
from luigi.contrib.s3 import S3Target
import luigi

import os
import pickle
import shutil


from .globals import *
CACHE_PATH = os.path.join(DATA_PATH, 'tmp/luigi_cache')

# try to set an S3_ROOT variable. this var will only be used if the user decided to "upload"
# cli.py will make sure this is actually a valid path if the user chose "upload"
S3_ROOT =  os.getenv('S3_ROOT')


from .scrape import *


class SaveLectureData(Task):
    '''
    given a URL, do all operations to find video download links and save data to cache file
    '''
    
    master_URL = Parameter()
    
    # NOTE: nothing is "required"

    def output(self):
        # extract unique class_id from utl
        class_id = self.master_URL.split('/')[4]
        # generate class specific cache file (meaning this task will only re-run on new courses)
        return LocalTarget(os.path.join(CACHE_PATH, class_id + '.pkl'), format=luigi.format.Nop)
    
    def run(self):
        # do setup
        driver = setup_and_login()

        # get sources
        player_page_source, player_type = get_player_page_source(driver, self.master_URL)

        # get video dict
        lecture_to_url = extract_lecture_links(player_page_source, player=player_type)

        # open all links
        title_to_page_source = open_lecture_links(driver, lecture_to_url, player=player_type)
        # extract data from network
        all_lecture_m3u8s = extract_m3u8s_from_netlog()
        
        # organize extracted data
        title_to_m3u8s = get_title_to_m3u8s(lecture_to_url, all_lecture_m3u8s, player=player_type)

        # find final download links
        title_to_best_m3u8 = get_title_to_download_links(title_to_m3u8s, player=player_type)
        
        # pack required data into dict
        data = {'title_to_page_source': title_to_page_source,
                'title_to_best_m3u8': title_to_best_m3u8,
                'player_type': player_type}
        
        with self.output().open('w') as cache:
            pickle.dump(data, cache)


#-------------------------------------------------------------------------------------------------------------------
#-------------------------------------------------- lecture tasks --------------------------------------------------
#-------------------------------------------------------------------------------------------------------------------

class DownloadLecture(Task):
    '''
    download a single lecture
    '''
    
    base_file_name = Parameter()
    url = Parameter()
    player = Parameter()
    timeout_max = IntParameter(default=None)
    
    # NOTE: nothing is "required"
    
    def output(self):
        return LocalTarget(os.path.join(VIDEO_PATH, clean_file_name(self.base_file_name) + '.mp4'),
                           format=luigi.format.Nop)
    
    def run(self):
        print('*'*25, 'started downloading lecture', '*'*25)
        
        with self.output().temporary_path() as tmp_path:
            download_lecture(url=self.url,
                             player=self.player,
                             base_file_name='THIS_IS_NOT_USED_HERE',
                             mp4_path=tmp_path,
                             timeout_max=self.timeout_max)


class UploadLecture(Task):
    '''
    upload a single lecture to S3 (will download lecture first if needed)
    '''
    
    base_file_name = Parameter()
    url = Parameter(default='')
    player = Parameter(default='')
    timeout_max = IntParameter(default=None)
    
    def requires(self):
        return DownloadLecture(base_file_name=self.base_file_name,
                               url=self.url,
                               player=self.player,
                               timeout_max=self.timeout_max)
    
    def output(self):
        return S3Target(S3_ROOT + '/' + clean_file_name(self.base_file_name) + '.mp4', format=luigi.format.Nop)
    
    def run(self):
        print('*'*25, 'started uploading lecture', '*'*25)
        
        with self.requires().output().open('r') as inf, self.output().open('w') as outf:
            outf.write(inf.read())


#-----------------------------------------------------------------------------------------------------------------
#-------------------------------------------------- slide tasks --------------------------------------------------
#-----------------------------------------------------------------------------------------------------------------

class PageSourceParameter(Parameter):
    '''
    an "ease of use" class so the full page source isn't printed to the console
    '''
    def serialize(self, x):
        return ''


class DownloadSlides(Task):
    '''
    download slides from a single lecture
    '''
    
    title = Parameter()
    page_source = PageSourceParameter()
    is_test_run = BoolParameter(default=True)
    
    # NOTE: nothing is "required"
    
    def output(self):
        timestamp_to_thumbnail_link = get_timestamp_to_thumbnail_link(self.page_source)
        
        # get the folder name
        folder_name = clean_file_name(self.title) + ' slides'
        
        timestamp_to_LocalTarget = {}
        for timestamp in timestamp_to_thumbnail_link:
            # get the formatted file name
            file_name = timestamp_to_file_name(timestamp)
            
            # get the full file path
            file_path = os.path.join(VIDEO_PATH, folder_name, file_name)
            
            timestamp_to_LocalTarget[timestamp] = LocalTarget(file_path, format=luigi.format.Nop)
        
        if self.is_test_run is True:
            return dict(list(timestamp_to_LocalTarget.items())[:2])
        return timestamp_to_LocalTarget
    
    
    def run(self):
        print('*'*25, 'started downloading slides', '*'*25)
        
        # if we are running we need to first delete the folder (if it already exists)
        # this is because luigi will get stuck on individual file renames (from tmp_path to path) if the file already exists
        folder_path = os.path.join(VIDEO_PATH, clean_file_name(self.title) + ' slides')
        try:
            shutil.rmtree(folder_path)
        except FileNotFoundError:
            pass
        
        timestamp_to_thumbnail_link = get_timestamp_to_thumbnail_link(self.page_source)
        
        # if doing a test, only download a few slides
        if self.is_test_run is True:
            timestamp_to_thumbnail_link = dict(list(timestamp_to_thumbnail_link.items())[:2])
        
        # download slides
        download_lecture_slides(timestamp_to_thumbnail_link, title="NOT_IN_USE", timestamp_to_LocalTarget=self.output())
    
    def complete(self):
        '''
        define a custome complete function that is "True" when "self.output()" is "{}"
        '''
        
        if len(self.output()) != 0:
            return super().complete()
        return True


class UploadSlides(Task):
    '''
    upload slides from a single lecture to S3 (will download slides first if needed)
    '''
    
    title = Parameter()
    page_source = PageSourceParameter()
    is_test_run = BoolParameter(default=True)
    
    def requires(self):
        return DownloadSlides(title=self.title, page_source=self.page_source, is_test_run=self.is_test_run)
    
    def output(self):
        # generate S3Target's from DownloadSlides LocalTarget's
        timestamp_to_S3Target = {timestamp: S3Target(LocalTarget_obj.path.replace(VIDEO_PATH, S3_ROOT).replace('\\', '/'),
                                                     format=luigi.format.Nop)
                                 for timestamp, LocalTarget_obj in self.requires().output().items()}
        
        # run over a small subset of is_test is True. this is redundant if DownloadSlides was already a subset
        if self.is_test_run is True:
            return dict(list(timestamp_to_S3Target.items())[:2])
        return timestamp_to_S3Target
    
    
    def run(self):
        print('*'*25, 'started uploading slides', '*'*25)
        
        # note: unlike in windows, you do not have to delete the lecture folder before writing/re-writing data
        # because renaming a file to an existing name does not cause a problem
        
        for timestamp in self.output():
            with self.input()[timestamp].open('r') as inf, self.output()[timestamp].open('w') as outf:
                outf.write(inf.read())
    
    def complete(self):
        '''
        define a custome complete function that is "True" when "self.output()" is "{}"
        '''
        
        if len(self.output()) != 0:
            return super().complete()
        return True


#-------------------------------------------------------------------------------------------------------------------
#-------------------------------------------------- wrapper tasks --------------------------------------------------
#-------------------------------------------------------------------------------------------------------------------

class ProcessAllLectures(Task):
    '''
    an abstract class that runs some task for each lecture
    '''
    
    master_URL = Parameter()
    process_slides = BoolParameter()
    is_test_run = BoolParameter(default=True)
    
    LectureProcess = NotImplemented
    SlideProcess = NotImplemented
    
    def requires(self):
        # fist we need to make sure we have the link data
        self.saved_lecture_data = SaveLectureData(master_URL=self.master_URL)
        yield self.saved_lecture_data
    
    def complete(self):
        return False
    # note: we always want to try to call run. it will do nothing if all subtasks have already happened.
    
    def run(self):
        # load saved data
        with self.saved_lecture_data.output().open('r') as cache: # TODO: HERE IS THE PROBLEM!
            data = pickle.load(cache)
        title_to_best_m3u8 = data['title_to_best_m3u8']
        player_type = data['player_type']
        title_to_page_source = data['title_to_page_source']
        
        # now we can process (download / upload) all the videos
        lecture_tasks = []
        slide_tasks = []
        for title, urls in title_to_best_m3u8.items():
            for url_num in range(len(urls)):
                # add lecture tasks
                full_title = title + ' - perspective' + str(url_num)
                
                task = self.LectureProcess(base_file_name=full_title,
                                           url=urls[url_num],
                                           player=player_type,
                                           timeout_max=1 if self.is_test_run else None)
                lecture_tasks.append(task)
            
            # add slide tasks if possible and wanted
            if player_type == 'panopto' and self.process_slides is True:
                task = self.SlideProcess(title=title,
                                         page_source=title_to_page_source[title],
                                         is_test_run=self.is_test_run)
                slide_tasks.append(task)
        
        # actually run the tasks
        build(lecture_tasks, local_scheduler=True) # TODO: add more workers?
        build(slide_tasks, local_scheduler=True) # TODO: add more workers?


class DownloadAllLectures(ProcessAllLectures):
    '''
    download all lectures
    '''
    LectureProcess = DownloadLecture
    SlideProcess = DownloadSlides


class UploadAllLectures(ProcessAllLectures):
    '''
    upload all lectures to S3 (will download lectures first if needed)
    '''
    LectureProcess = UploadLecture
    SlideProcess = UploadSlides

