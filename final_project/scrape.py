# basic webdriver imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
# imports for waiting
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from bs4 import BeautifulSoup
import os
import json
import requests
import re
from tqdm import tqdm
import time


# get credentials
CANVAS_USERNAME = os.getenv('CANVAS_USERNAME')
CANVAS_PASSWORD = os.getenv('CANVAS_PASSWORD')

from .globals import *
LOG_PATH = os.path.join(DATA_PATH, 'tmp/net_log.json')
DRIVER_PATH = os.path.join(DATA_PATH, 'drivers/chromedriver')

DEFAULT_TIMEOUT = 30


# SOME INITIAL RESEARCH:
# chomedriver: https://sites.google.com/a/chromium.org/chromedriver/ / https://chromedriver.chromium.org/
# chromium command line switches: https://peter.sh/experiments/chromium-command-line-switches/#net-log-capture-mode
#     important flags: '--log-net-log', '--net-log-capture-mode' / '--enable-logging --v=1'
#     How to capture a NetLog dump: https://www.chromium.org/for-testers/providing-network-details
# canvas tutorial: https://towardsdatascience.com/controlling-the-web-with-python-6fceb22c5f08


def generate_driver():
    '''
    return a fully configured chrome driver
    '''
    
    # configure options
    chrome_options = ChromeOptions()
    chrome_options.add_argument('--log-net-log={}'.format(LOG_PATH))
    # note: the '--log-net-log' switch is of *vital* importance to this projct as it records network activity
    
    # start the driver
    driver = webdriver.Chrome(executable_path=DRIVER_PATH, options=chrome_options)
    
    return driver


def setup_and_login(default_2FA=True):
    '''
    automatically walk through the process of starting Canvas and passing 2FA
    
    default_2FA (bool) : if true, automatically 'call' the fist 2FA method presented
    '''
    
    # step 0: start a configured driver
    driver = generate_driver()
    
    # step 0.5: open the base canvas url --> triggers a login scree
    driver.get('https://canvas.harvard.edu/')
    
    
    #-------------------------------------------------------
    #-------------------- step 1: login --------------------
    #-------------------------------------------------------
    
    # wait for the 'username' element to indicate the login page has loaded
    _ = WebDriverWait(driver, DEFAULT_TIMEOUT).until(EC.presence_of_element_located((By.ID, 'username')))
    
    # input username
    username_box = driver.find_element_by_id('username') # note: could just remove this line and use the WebDriverWait return
    username_box.send_keys(CANVAS_USERNAME)
    
    # input password
    pass_box = driver.find_element_by_id('password')
    pass_box.send_keys(CANVAS_PASSWORD)
    
    # click submit
    login_button = driver.find_element_by_id('submitLogin')
    login_button.click()
    
    
    #--------------------------------------------------------------
    #-------------------- step 2: get past 2FA --------------------
    #--------------------------------------------------------------
    
    # select the default 2FA method
    # note: if this is not used, the user must select and trigger the 2FA manually
    if default_2FA is True:
        # wait for 2FA iframe to load and switch to it
        _ = WebDriverWait(driver, DEFAULT_TIMEOUT).until(EC.frame_to_be_available_and_switch_to_it('duo_iframe'))
        
        # click the 'call' button
        call_button = driver.find_element_by_css_selector('.positive.auth-button')
        call_button.click()
    
    
    # wait for dashboard to load
    print('INFO: if 2FA is not completed within 120s, this program will exit automatically')
    _ = WebDriverWait(driver, 120).until(EC.presence_of_element_located((By.ID, 'dashboard')))
    
    # return the authenticated driver object
    return driver


def get_player_page_source(driver, lecture_URL, player=None):
    '''
    given a authenticated driver, a lecture URL, (and optionally) the player type: return the player page source after
    loading iframes correctly
    
    return: player_page_source, player_name
    '''
    
    # if a player was slected, make sure it is valid
    if player is not None and player not in ('matterhorn', 'panopto'):
        raise ValueError(f'invalid player selected. player "{player}" is not in ("matterhorn", "panopto")')
    
    # load the url in the driver
    driver.get(lecture_URL)

    # wait for the video iframe to become visible and switch to it
    _ = WebDriverWait(driver, DEFAULT_TIMEOUT).until(EC.frame_to_be_available_and_switch_to_it('tool_content'))
    
    # try to figure out what player is being used based on HTML clues (if no player given)
    # note: this is probably very unstable...
    if player is None:
        initial_page = BeautifulSoup(driver.page_source)
        head_element = initial_page.find('head')
        
        description_element = head_element.find('meta', attrs={'name': 'description'})

        if description_element['content'] == 'HUDCE Publication Listing':
            player = 'matterhorn'
        elif description_element['content'] == 'Capture, manage, and search all your video content.':
            player = 'panopto'
        else:
            raise Exception('looks like the HTML changed and player auto detection is broken')
        
    # get player specific class for 'wait' below
    if player == 'matterhorn':
        element_class = '.item.ng-scope'
    elif player == 'panopto':
        element_class = '.thumbnail-row.draggable'
    
    # wait for the videos to load into the frame (class depends on player)
    _ = WebDriverWait(driver, DEFAULT_TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, element_class)))
    # note: 'EC.presence_of_all_elements_located' has same wait effect because it only waits for first element
    
    # return the player page source
    return driver.page_source, player


def extract_lecture_links(player_page_source, player):
    '''
    given a player_page_source and the type of player it came from, extract a 'lecture: url' dict
    '''
    
    player_page = BeautifulSoup(player_page_source)
    
    lecture_to_url = {}
    
    if player == 'matterhorn':
        items_container = player_page.find('div', 'items-container ng-scope') # lowest level to contain list of vids
        # note: no need to scope to 'items-container ng-scope' as other tag is specific enough
        #       but it makes me happy :p
        
        for video in items_container.find_all('div', 'item ng-scope'):
            # extract the title attr
            title_element = video.find('div', 'publication-title auto-launch')
            
            # extract the link attr
            link_element = video.find('a', 'live-event item-link')
            
            title = title_element.text.strip()
            link = 'https:' + link_element['href']
            lecture_to_url[title] = link
    
    elif player == 'panopto':
        details_table = player_page.find('table', 'details-table') # lowest level to contain list of vids
        # note: no need to scope to 'details-table' as other tag is specific enough
        #       but it makes me happy :p
        
        for video in details_table.find_all('tr', 'thumbnail-row draggable'):
            # extract the title/link attr
            title_element = video.find('a', 'detail-title')
            
            title = title_element.text.strip()
            link = title_element['href']
            lecture_to_url[title] = link
    
    return lecture_to_url


def open_lecture_links(driver, lecture_to_url, player):
    '''
    given a driver, a lecture_to_url dict, and a player: open each link in lecture_to_url
    
    this allows the driver to track the network activity generated from each lecture page
    '''
    
    # (probably not needed) make sure the player is valid
    assert(player in ('panopto', 'matterhorn'))
    
    title_to_page_source = {}
    
    # open each link
    for title, link in lecture_to_url.items():
        # go to the link
        driver.get(link)
        
        # wait for the page to fully load
        if player == 'matterhorn':
            # wait for the play button to appear
            _ = WebDriverWait(driver, DEFAULT_TIMEOUT).until(EC.presence_of_element_located(
                (By.ID, 'paella_plugin_PlayButtonOnScreen')))
        elif player == 'panopto':
            # wait for the loading image to appeaer
            _ = WebDriverWait(driver, DEFAULT_TIMEOUT).until(EC.presence_of_element_located((By.ID, 'loadingMessage')))
            # waif for the loading image to disappear (finished loading)
            _ = WebDriverWait(driver, DEFAULT_TIMEOUT).until(EC.invisibility_of_element_located((By.ID, 'loadingMessage')))
            
            # save the page source
            title_to_page_source[title] = driver.page_source
    
    # we are done with driver so we can 'quit' it
    driver.quit()
    
    return title_to_page_source


# ----------------------------------------------------------------------------------------------------------------------
#-------------------------------------------------- slide code STARTS --------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------

def get_timestamp_to_thumbnail_link(page_source):
    '''
    given a lecture page_source extract all thumbnail links
    '''
    
    page = BeautifulSoup(page_source)

    # locate the thumbnail list
    thumbnailList_element = page.find('ol', id='thumbnailList')

    # extact data
    timestamp_to_thumbnail_link = {}

    for thumbnail in thumbnailList_element.find_all('li', class_='thumbnail'):
        # thumbnail link
        img_element = thumbnail.find('img')
        thumbnail_link = img_element['data-src']

        # extact timestamp
        timestamp_element = thumbnail.find('div', class_='thumbnail-timestamp')
        timestamp = timestamp_element.text

        timestamp_to_thumbnail_link[timestamp] = thumbnail_link
    
    # note: because the key is the timestamp, there can be occasions where a slide change gets lost because multiple happen
    # in the same second. however this really shouldn't matter because slides shown for less then 1s are probably not important
    
    return timestamp_to_thumbnail_link


def timestamp_to_file_name(timestamp):
    '''
    given a simestamp (string) convert to a nicely formatted filename
    '''
    
    split = ('0:' + timestamp).split(':')
    file_name = '{:02}_{:02}_{:02}'.format(int(split[-3]), int(split[-2]), int(split[-1])) + '.jpg'
    return file_name


def download_lecture_slides(timestamp_to_thumbnail_link, title, timestamp_to_LocalTarget=None):
    '''
    download lecture slides for one lecture
    '''
    
    with requests.Session() as session:
        for timestamp, thumbnail_link in timestamp_to_thumbnail_link.items():
            # get the initial thumbnail
            r1 = session.get(thumbnail_link)
            thumbnail_url = r1.url
            assert(r1.status_code == 200)

            # often, there is an (easily findable) high resolution image behind the thumbnail
            image_url = thumbnail_url.replace('thumbs', 'images')
            r2 = session.get(image_url)

            # download the best image you could find (sometimes, this will just the the normal thumbnail)
            if r2.status_code == 200:
                content = r2.content
            else:
                content = r1.content
            
            # if runnning without luigi
            if timestamp_to_LocalTarget is None:
                # get folder name
                folder_name = clean_file_name(title) + ' slides'
                # make the folder if needed
                os.makedirs(os.path.join(VIDEO_PATH, folder_name), exist_ok=True)

                # get file name
                file_name = timestamp_to_file_name(timestamp)
                
                # get the full file path
                file_path = os.path.join(VIDEO_PATH, folder_name, file_name)
                
                # save the image
                with open(file_path, 'wb') as f:
                    f.write(content)
            else: # if running in luigi
                with timestamp_to_LocalTarget[timestamp].open('w') as f:
                    f.write(content)

# --------------------------------------------------------------------------------------------------------------------
#-------------------------------------------------- slide code ENDS --------------------------------------------------
# --------------------------------------------------------------------------------------------------------------------

def extract_m3u8s_from_netlog():
    '''
    extract all .m3u8 links from network log
    '''
    
    # read the json file to a string
    with open(LOG_PATH, 'r') as log_file:
        json_str = log_file.read()
    
    # try to parst the json string normally
    try:
        json_obj = json.loads(json_str)
    except json.JSONDecodeError:
        # try to load the data by patching the end of the file
        try:
            json_data = json.loads(json_str[:-2] + ']}')
        except json.JSONDecodeError:
            print('INFO: looks like you got unlucky... (maybe a buffer not flusing?). try running this again!')
            raise
    # NOTE: the reason you often have to patch the net log is because calling driver.quit() will kill chrome without
    # writing the closing tags on the net log
    
    all_lecture_m3u8s = []
    for event in json_data['events']:
        if 'params' in event:
            params = event['params']
            
            if params.get('network_isolation_key', None) in ('https://matterhorn.dce.harvard.edu',
                                                             'https://harvard.hosted.panopto.com'):
                if '.m3u8' in params['url']:
                    all_lecture_m3u8s.append(params['url'])
    
    return all_lecture_m3u8s


def get_title_to_m3u8s(lecture_to_url, all_lecture_m3u8s, player):
    '''
    build a dict that links titles to m3u8s using lecture_to_url (extracted from HTML) and all_lecture_m3u8s (from net log)
    '''
    
    # ----------------------------------------------------------------------------------------------------------------------
    # def id1: the first string of 32 hex vals
    # def id2: the first 32 hex vals of the second string of 64 hex vals
    # for both players each id1 has multiple id2's
    
    # assume: we build an id1_to_m3u8s dict that stores all m3u8s for a given id1
    
    # in matterhorn, the lecture_id is id1. we can easily find all m3u8s by plugging id1 into id1_to_m3u8s
    # in panopto, the lecture_id is id2. we first need to find the (base) id1 which we can then plug into id1_to_m3u8s
    # ----------------------------------------------------------------------------------------------------------------------
    
    # build a simple dict linking title to lecture_id
    title_to_lecture_id = {title: m3u8.split('id=')[1] for title, m3u8 in lecture_to_url.items()}
    
    # build a dict that links from the id1 (the base id) to all m3u8's that have id1
    id1_to_m3u8s = {}
    for m3u8 in all_lecture_m3u8s:
        id1 = m3u8.split('/')[4]
        
        # note: this will build a 1-1 dict
        if id1 not in id1_to_m3u8s:
            id1_to_m3u8s[id1] = []
        id1_to_m3u8s[id1].append(m3u8)
    
    if player == 'matterhorn':
        # in matterhorn, the lecture_id is id1 (the base id) so we can just grab the m3u8s directly
        return {title: id1_to_m3u8s[id1] for title, id1 in title_to_lecture_id.items()}
    
    elif player == 'panopto':
        id2_to_id1 = {}
        for m3u8 in all_lecture_m3u8s:
            id1 = m3u8.split('/')[4]
            id2 = m3u8.split('/')[5][:36]
            id2_to_id1[id2] = id1 # this will overwrite a few times (which is fine)
        # note: this will build a many-to-one dict

        # in panopto, the lecture_id is id2 (the second id) so we need to first get the (base) id1 for each id2
        return {title: id1_to_m3u8s[id2_to_id1[id2]] for title, id2 in title_to_lecture_id.items()}


def get_title_to_download_links(title_to_m3u8s, player):
    '''
    extract final download links from list of possible m3u8 files
    '''
    
    title_to_best_m3u8 = {}

    for title, m3u8_list in title_to_m3u8s.items():
        max_resolution_m3u8s = []
        
        # for each m3u8 url...
        for m3u8 in m3u8_list:
            
            # get the full content
            m3u8_content = requests.get(m3u8).content.decode()
            
            # if we're looking at a 'master' file (a file with links to other files), do stuff...
            if '#EXT-X-STREAM-INF' in m3u8_content:
                #-------------------- find the m3u8 varient with the max resolution --------------------
                #---------------------------------------------------------------------------------------
                
                resolution_dict = {}
                
                # convert to line-by-line content
                m3u8_content = m3u8_content.splitlines()
                
                # itterate over the lines...
                for i in range(len(m3u8_content)):
                    line = m3u8_content[i]

                    # TODO: add explanation here
                    if line.startswith('#EXT-X-STREAM-INF'):
                        # use a regex to match some '<num>x<num>'. this is the resolution (found after a 'RESOLUTION=' tag)
                        resolution = re.findall('\d*x\d*', line)[0]
                        
                        # grab the next line which stores the extension of the resolution variant
                        m3u8_extension = m3u8_content[i+1]
                        
                        resolution_dict[resolution] = m3u8_extension
                
                # GET THE MAX
                max_prod = -1
                max_resolution = None
                for resolution in resolution_dict.keys():
                    x, y = resolution.split('x')
                    prod = int(x)*int(y)

                    if prod > max_prod:
                        max_prod = prod
                        max_resolution = resolution
                
                # get the m3u8 extension at the max resolution
                m3u8_extension = resolution_dict[max_resolution]
                
                #-------------------- find the full link using the base and the max resolution extension --------------------
                #------------------------------------------------------------------------------------------------------------
                
                if player == 'matterhorn':
                    base_re = 'https://dvgni8clk4vbh.cloudfront.net/engage-player/[\w-]*/'
                elif player == 'panopto':
                    base_re = 'https://d2y36twrtb17ty.cloudfront.net/sessions/[\w-]*/[.\w-]*/'
                
                # extract the base from the m3u8 link
                base_m3u8 = re.findall(base_re, m3u8)[0]
                
                if player == 'matterhorn':
                    full_m3u8 = base_m3u8 + m3u8_extension[3:]
                    m3u8_content = requests.get(full_m3u8).content.decode()
                    
                    # extract the mp4 link from the m3u8 content
                    mp4_extension = re.findall('../.*.mp4', m3u8_content)[0]
                    
                    # add the mp4 link to the list
                    max_resolution_m3u8s.append(base_m3u8 + mp4_extension[3:])
                elif player == 'panopto':
                    full_m3u8 = base_m3u8 + m3u8_extension
                    
                    # add the ts list
                    max_resolution_m3u8s.append(full_m3u8)
        
        # add max_resolution_m3u8 list to the main dict
        title_to_best_m3u8[title] = max_resolution_m3u8s
    
    return title_to_best_m3u8


def download_lecture(url, player, base_file_name, mp4_path=None, timeout_max=None):
    '''
    download a single lecture
    '''
    
    # if mp4_path is unset, set it using VIDEO_PATH and base_file_name
    if mp4_path is None:
        mp4_path = os.path.join(VIDEO_PATH, clean_file_name(base_file_name) + '.mp4')
    
    # set a hard cap of 60min (*WAY* more time then needed) for a single download if no time is specified
    if timeout_max is None:
        timeout_max = 60*60
    
    if player == 'matterhorn':
        stream = requests.get(url, stream=True)
        
        # download the video by making many small requests
        start_time = time.time()
        with open(mp4_path, 'wb') as f:
            for chunk in tqdm(stream.iter_content(chunk_size=1048576), desc='downloading lecture'):
                f.write(chunk)
                
                # break if over timeout_max
                time_delta = time.time() - start_time
                if time_delta > timeout_max:
                    print('broke from loop after {} seconds'.format(time_delta))
                    break
    
    if player == 'panopto':
        m3u8_content = requests.get(url).content.decode()
        
        # extact a ts list from the m3u8 content
        ts_list = []
        for line in m3u8_content.splitlines():
            if line.endswith('.ts'):
                ts_list.append(url.replace('index.m3u8', line))
        
        # download the video by looping over ts files
        with open(mp4_path, 'wb') as mp4:
            start_time = time.time()
            
            for ts_url in tqdm(ts_list, desc='downloading lecture'):
                mp4.write(requests.get(ts_url).content)

                # break if over timeout_max
                time_delta = time.time() - start_time
                if time_delta > timeout_max:
                    print('broke from loop after {} seconds'.format(time_delta))
                    break


#--------------------------------------------------------------------------------------------------------------
#-------------------------------------------------- not used --------------------------------------------------
#--------------------------------------------------------------------------------------------------------------

def download_all_lecture_slides(title_to_page_source):
    '''
    given a title_to_page_source (returned from "open_lecture_links"), download all lecture slides for all lectures
    '''
    
    for title, page_source in tqdm(title_to_page_source.items(), desc='downloading all lecture slides'):
        timestamp_to_thumbnail_link = get_timestamp_to_thumbnail_link(page_source)
        download_lecture_slides(timestamp_to_thumbnail_link, title)


def download_all_videos(master_URL, timeout_max=None):
    # do setup
    driver = setup_and_login()
    
    # get sources
    player_page_source, player_type = get_player_page_source(driver, master_URL)
    
    # get video dict
    lecture_to_url = extract_lecture_links(player_page_source, player=player_type)
    
    # open all links
    _ = open_lecture_links(driver, lecture_to_url, player=player_type)
    # extract data from network
    all_lecture_m3u8s = extract_m3u8s_from_netlog()
    
    # organize extracted data
    title_to_m3u8s = get_title_to_m3u8s(lecture_to_url, all_lecture_m3u8s, player=player_type)
    
    # find final download links
    title_to_best_m3u8 = get_title_to_download_links(title_to_m3u8s, player=player_type)
    
    # download all videos
    for title, urls in title_to_best_m3u8.items():
        for url_num in range(len(urls)):
            full_title = title + ' - perspective' + str(url_num)
            download_lecture(urls[url_num], player=player_type, lecture_name=full_title, timeout_max=timeout_max)

