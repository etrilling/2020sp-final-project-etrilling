# class DownloadMetadata(ExternalTask):
#     master_URL = Paramater()
    
#     def requires():
#         nothing
    
#     def output():
#         LocalTarget('metadata.plk')
    
#     def run():

#         # do setup
#         driver = setup_and_login()

#         # get sources
#         player_psource, player_type = get_player_psource(driver, master_URL)

#         # get video dict
#         video_dict = extract_video_links(player_psource, player=player_type)

#         open_video_links(driver, video_dict, player=player_type, URL=master_URL) # pass in original url

#         all_video_urls = get_video_urls(LOG_PATH)

#         title_to_urls = get_title_to_urls(video_dict, all_video_urls, player=player_type)

#         if player_type == 'matterhorn':
#             title_to_urls = get_title_to_urls2(title_to_urls)
        
#         data = {'title_to_urls': title_to_urls, 'player_type': player_type}
        
#         with open('data.plk', 'wb') as f:
#             pickle.dump(f, data)
    

# class DownloadAllVideos(Task):
#     def requires():
#         return DownloadMetadata()
    
#     def output():
#         with open('data.plk', 'rb') as f:
#             data = pickle.load(f)
#         title_to_urls = data['title_to_urls']
#         player_type = data['player_type']
        
#         download_tasks = []

#         for title, urls in title_to_urls.items():
#             for url_num in range(len(urls)):
#                 full_title = title + ' - ' + str(url_num) + ".mp4"

#                 task = DownloadVideo(fname=full_title, download_video_params=(urls[url_num], player=player_type,
#                                                                               video_name=full_title, max_time=10)) # TODO: update time
#                 download_tasks.append(task)

#         return download_tasks
    
#     def run():
#         # I don't think we need to run anything
#         pass


# class DownloadVideo(Task):
#     fname = Paramater()
#     download_video_params = Paramater()
    
#     def requires():
#         nothing
    
#     def output():
#         LocalTarget(fname)
    
#     def run():
#         download_video(download_video_params)
