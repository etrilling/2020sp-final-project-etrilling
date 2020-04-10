from selenium import webdriver
from selenium.webdriver.chrome.options import Options
# imports for waiting
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import os

from bs4 import BeautifulSoup

import json

import requests
import re
from tqdm import tqdm

import time


# set constants
USERNAME = os.getenv('CANVAS_USERNAME')
PASSWORD = os.getenv('CANVAS_PASSWORD')

LOG_PATH = os.path.abspath('./../temp_data/net_log.json')
VIDEO_PATH = os.path.abspath('./../videos')


def generate_driver():
    # configure options
    # note: the "--log-net-log" switch is of vital importance to this projct as it records all network activity
    chrome_options = Options()
    chrome_options.add_argument('--log-net-log={}'.format(LOG_PATH))
    
    # start the driver
    driver = webdriver.Chrome(executable_path='./../drivers/chromedriver', options=chrome_options) # TODO: add some comment about drivers...
    
    return driver


def setup_and_login(default_2FA=True):
    # step 0: start a configured driver
    driver = generate_driver()
    
    # step 0.5: open the base canvas url
    driver.get('https://canvas.harvard.edu/')
    
    #---------- step 1: login ----------
    # wait for the "username" element to indicate the page has loaded
    _ = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "username")))
    
    # input username
    username_box = driver.find_element_by_id('username') # note: could just remove this line and use the WebDriverWait return
    username_box.send_keys(USERNAME)
    
    # input password
    pass_box = driver.find_element_by_id('password')
    pass_box.send_keys(PASSWORD)
    
    # click submit
    login_button = driver.find_element_by_id('submitLogin')
    login_button.click()
    
    #---------- step 2: get past 2 factor ----------
    # TODO: add some comments/instructions here
    if default_2FA is True:
        # wait for iframe to load and switch to it
        _ = WebDriverWait(driver, 15).until(EC.frame_to_be_available_and_switch_to_it('duo_iframe'))
        
        # click the "call" button
        call_button = driver.find_element_by_css_selector('.positive.auth-button')
        call_button.click()
    
    
    # wait for dashboard to load
    _ = WebDriverWait(driver, 120).until(EC.presence_of_element_located((By.ID, "dashboard")))
    
    # return the driver object
    return driver


def get_player_psource(driver, URL, player=None):
    """given a logged-in driver, player type, and a URL: return the page source after loading iframs correctly"""
    
    # load the url in the driver
    driver.get(URL)

    # wait for the iframe to become visible and switch to it
    _ = WebDriverWait(driver, 15).until(EC.frame_to_be_available_and_switch_to_it('tool_content'))
    
    # try to figure out what player is being used based on HTML clues (if no player given)
    # note: this is probably very unstable...
    if player is None:
        initial_page = BeautifulSoup(driver.page_source)
        head_attr = initial_page.find("head")
        
        description_attr = head_attr.select("[name=description]")
        assert(len(description_attr) == 1)

        if description_attr[0]['content'] == "HUDCE Publication Listing":
            player = "matterhorn"
        elif description_attr[0]['content'] == "Capture, manage, and search all your video content.":
            player = "panopto"
        else:
            raise Exception("looks like the HTML changed and auto player detection is broken")
    
    # get player specific class for "wait" below
    if player == "matterhorn":
        element_class = ".item.ng-scope"
    elif player == "panopto":
        element_class = ".thumbnail-row.draggable"
    else:
        raise Exception("must select valid player")
    
    # wait for the videos to load into the frame (exact wait command depends on player)
    _ = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, element_class)))
    # note: "EC.presence_of_all_elements_located" has same wait effect because it only waits for first element
    
    # return the player page source
    return driver.page_source, player


def extract_video_links(page_source, player):
    """
    given a page_source and the type of player it came from, extract a 'video: link' dict
    
    note: I'm keeping all the 'asserts' just because HTML is liable to change with updates from Harvard devs...
    """
    
    page = BeautifulSoup(page_source)
    
    video_dict = {}
    
    if player == "matterhorn":
        # note: no need to scope to "items-container ng-scope" as other tag is specific enough
        #       but it makes me happy :p
        items_container = page.find_all("div", "items-container ng-scope") # note: lowest level to contain list of vids
        assert(len(items_container) == 1)
        
        for video in items_container[0].find_all("div", "item ng-scope"):
            # extract the title attr
            title_attr = video.find_all("div", "publication-title auto-launch")
            assert(len(title_attr) == 1)
            
            # extract the link attr
            link_attr = video.find_all("a", "live-event item-link")
            assert(len(link_attr) == 1)

            title = title_attr[0].text.strip()
            link = 'https:' + link_attr[0]['href']

            video_dict[title] = link
    
    elif player == "panopto":
        # note: no need to scope to "details-table" as other tag is specific enough
        #       but it makes me happy :p
        details_table = page.find_all("table", "details-table") # note: lowest level to contain list of vids
        assert(len(details_table) == 1)
        
        for video in details_table[0].find_all("tr", "thumbnail-row draggable"):
            # extract the title/link attr
            title_attr = video.find_all("a", "detail-title")
            assert(len(title_attr) == 1)
            
            title = title_attr[0].text.strip()
            link = title_attr[0]['href']
            
            video_dict[title] = link
    
    else:
        raise Exception("must select valid player")
    
    return video_dict


def open_video_links(driver, video_dict, player, URL=None):
    # make sure we are using a valid player
    if player not in ('panopto', 'matterhorn'):
        raise Exception("must select valid player - looks like something went wrong in previous code")
    
    # if using 'panopto', you need to visit this page or 'panopto' won't authenticate. yay... I love having more steps...
    if player == 'panopto':
        # make sure a URL was provided
        if URL is None:
            raise Exception("must add URL for panopto player")
        
        driver.get(URL)
        _ = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, 'tool_content')))
    
    # open each link
    for title, link in video_dict.items():
        # go to the link
        driver.get(link)
        
        # wait for the page to load (dependent on player)
        if player == 'matterhorn':
            # note: id="playerContainer_videoContainer_container" is the "div" wrapping video streams (there can be multiple)
            #       however, it loads too quickly. waiting for the play button to become visible it very reliable though
            
            _ = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, 'paella_plugin_PlayButtonOnScreen')))
        elif player == 'panopto':
            # note id="primaryVideo" contains 'src="blob..."' but does not work because it loads too quickly
            #      instead, we wait for loading element to be part of page then wait for it to become invisible (meaning loaded)
            
            _ = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, 'loadingMessage')))
            _ = WebDriverWait(driver, 15).until(EC.invisibility_of_element_located((By.ID, 'loadingMessage')))
    
    # we are done with driver so we can "quit" it
    driver.quit()


def get_video_urls(log_path):
    # note: it was intentional to put the "with" on the inside of the try (even though it duplicates them)
    # otherwise, you have to start a new one to call the "log_file.read()"...
    
    # try to load the data normally
    try:
        with open(log_path, 'r') as log_file:
            json_data = json.load(log_file)
    except json.JSONDecodeError:
        # try to load the data by patching the end of the file
        print('note: in JSON exception. trying to patch file...')
        with open(log_path, 'r') as log_file:
            json_str = log_file.read()
        json_data = json.loads(json_str[:-2] + ']}')
    
    video_urls = []
    for event in json_data['events']:
        if 'params' in event:
            params = event['params']

            if params.get('network_isolation_key', None) in ('https://matterhorn.dce.harvard.edu',
                                                             'https://harvard.hosted.panopto.com'):
                if params['url'][-4:] == 'm3u8':
                    video_urls.append(params['url'])
    
    return video_urls


def get_title_to_urls(video_dict, all_video_urls, player):
    
    def get_title_to_id(video_dict):
        """get a title_to_id dict - where id comes from the list page"""
        title_to_id = {}
        for title, link in video_dict.items():
            id_ = link.split('id=')[1]
            title_to_id[title] = id_
        return title_to_id
    
    # TODO: ADD COMMENT HERE!
    id1_to_urls = {}
    for url in all_video_urls:
        id1 = url.split('/')[4] # 17
        
        # note: this will build a 1-1 dict
        if id1 not in id1_to_urls:
            id1_to_urls[id1] = []
        id1_to_urls[id1].append(url)
    
    
    if player == 'panopto':
        title_to_id2 = get_title_to_id(video_dict) # in panopto, the id is id2
        
        # ADD COMMENT HERE!
        id2_to_id1 = {}
        for url in all_video_urls:
            id1 = url.split('/')[4] # 17
            id2 = url.split('/')[5][:36] # 25

            # note: this will build a 1-1 dict when the initial set had 1-many
            id2_to_id1[id2] = id1 # this will overwrite a few times (which is fine)

        # combine dicts to get title_to_urls
        title_to_urls = {title: id1_to_urls[id2_to_id1[id2]] for title, id2 in title_to_id2.items()}
    
    if player == 'matterhorn':
        title_to_id1 = get_title_to_id(video_dict) # in matterhorn, the id is id1
        
        title_to_urls = {title: id1_to_urls[id1] for title, id1 in title_to_id1.items()}
    
    return title_to_urls


def get_title_to_urls2(title_to_urls):
    title_to_urls2 = {}

    for title, url_list in tqdm(title_to_urls.items()):
        url_list2 = []
        
        # for each m3u8 url...
        for url in url_list:
            
            # get the full content
            m3u8_content = requests.get(url).content.decode()
            
            if '#EXT-X-STREAM-INF' in m3u8_content:
                variant_dict = {}
                
                # convert to line-by-line content
                m3u8_content = m3u8_content.splitlines()
                
                # itterate over the lines...
                for i in range(len(m3u8_content)):
                    line = m3u8_content[i]

                    # TODO: add explanation here
                    if line.startswith('#EXT-X-STREAM-INF'):
                        # use a regex to match some "<num>x<num>" (this is the resolution - found after a 'RESOLUTION=' tag)
                        resolution = re.findall('\d*x\d*', line)[0]
                        # grab the next line which stores the url of the m3u8 variant
                        next_line = m3u8_content[i+1]
                        # add data to dict
                        variant_dict[resolution] = next_line
                
                # GET THE MAX
                max_prod = -1
                max_resolution = None
                for resolution in variant_dict.keys():
                    x, y = resolution.split('x')
                    prod = int(x)*int(y)

                    if prod > max_prod:
                        max_prod = prod
                        max_resolution = resolution
                
                # get the m3u8 extension at the max resolution
                m3u8_extension = variant_dict[max_resolution]
                
                # get the base url from the current url (any url in list would also work - because they all have the same base)
                base_url = re.findall('https://dvgni8clk4vbh.cloudfront.net/engage-player/[\w-]*/', url)[0]
                
                full_m3u8_url = base_url + m3u8_extension[3:]
                
                # TODO: update var name
                m3u8_content = requests.get(full_m3u8_url).content.decode()

                mp4_extension = re.findall('../.*.mp4', m3u8_content)[0]
                
                url_list2.append(base_url + mp4_extension[3:])

        # add url_list2 to the main dict
        title_to_urls2[title] = url_list2
    
    return title_to_urls2


def download_video(URL, player, video_name, max_time=None):
    if max_time is None:
        max_time = 60*20 # setting a hard cap of 20min for a single download
    
    mp4_path = os.path.join(VIDEO_PATH, video_name)
    
    if player == 'matterhorn':
        assert(URL[-3:] == 'mp4') # make sure I didn't pass in bad URL
        
        stream = requests.get(URL, stream=True)
    
        start_time = time.time()
        with open(mp4_path, 'wb') as f:
            for chunk in tqdm(stream.iter_content(chunk_size=1048576)):
                f.write(chunk)
                
                time_delta = time.time() - start_time
                if time_delta > max_time:
                    print('broke from loop after {} seconds'.format(time_delta))
                    break
    
    if player == 'panopto':
        # note: I got some inspiration from this tiny project (https://github.com/onesafe/m3u8_to_mp4)
        
        assert(URL[-4:] == 'm3u8') # make sure I didn't pass in bad URL
        
        # get content of m3u8 file
        m3u8_content = requests.get(URL).content.decode()
        
        # build a list of ts files
        ts_list = []
        for line in m3u8_content.splitlines():
            if line.endswith('.ts'):
                ts_list.append(line)
        
        # download the video by looping over ts files
        with open(mp4_path, 'wb') as mp4:
            start_time = time.time()

            for ts in tqdm(ts_list):
                ts_url = URL.replace('index.m3u8', ts)
                mp4.write(requests.get(ts_url).content)

                # break if over max_time
                time_delta = time.time() - start_time
                if time_delta > max_time:
                    print('broke from loop after {} seconds'.format(time_delta))
                    break

