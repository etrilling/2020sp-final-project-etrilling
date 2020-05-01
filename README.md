# CSCI E-29 Final Project

### Short Description
Given a link to a "Recorded Lectures" page on Canvas, download all lectures and all lecture slides (if applicable AND wanted). If desired, once lectures are downloaded, upload a copy to an S3 bucket.

This is designed to work with both possible Harvard players. I refer to the "normal" player as the "Matterhorn" player (as all lecture links look like `matterhorn.dce.harvard.edu...`. The other player is called "Panopto" (with links like `harvard.hosted.panopto.com...`. When downloading from the Panopto player, slides can be downloaded if desired (by use of a command line flag).


### Setup

**Requirement**: have a Chromium based browser installed (for most people this will just be Google Chrome).

1. Clone this repository to your computer.


2. Setup the project virtual environment by running `pipenv install` (this assumes `pipenv` is already installed)


3. Add your information to a `.env` file.
    - CANVAS_USERNAME=XXX
    - CANVAS_PASSWORD=XXX
    - AWS_ACCESS_KEY_ID=XXX
    - AWS_SECRET_ACCESS_KEY=XXX
    - S3_ROOT=s3://BUCKET_NAME/PATH `example: s3://etrilling-cscie29/recorded_lectures`
    - (optional) VIDEO_PATH=DOWNLOAD_LOCATION_FOR_VIDEOS `default: ./data/videos`


4. Please visit https://chromedriver.chromium.org/downloads and follow the instructions to download the correct ChromeDriver file for your computer. (if needed, unzip the download to get the `chromedriver` file). Place the `chromedriver` file in `./data/drivers/`.


5. run `pipenv run python -m final_project <COMMAND> <TARGET_URL> [--full] [--process_slides]`
    - `<COMMAND>`: one of `download` or `upload`. NOTE: `upload` will start by calling `download`.
    <br><br>
    
    - `<TARGET_URL>`: the url of a "Recorded Lectures" page on Canvas.\
    Example:
    ![](./imgs/canvas_example_1.jpg)
    Here, the correct `<TARGET_RUL>` is `https://canvas.harvard.edu/courses/69812/external_tools/22940`
    <br><br>
    
    - `--full`: when set, the full length lectures and slides (if applicable AND wanted) will be downloaded. When not set, each lecture will only download for 1 second and only 2 slides will be downloaded (if applicable AND wanted). This is meant as a test for the user.
    <br><br>
    
    - `--process_slides`: if the player type is Panopto and this flag is set, slides will be processed (downloaded / uploaded) along with the lectures.


6. If you're downloading from any given Canvas link for the first time, an instance of Google Chrome will pop up and autotomatially log you into Canvas. **You will need to manually confirm the automatic 2FA call**. Once logged in, the webdriver will proceed to open each lecture. Please do not click on anything while this is happening (if you do, you may need to re-run the command). Once finished, the Google Chrome instance will close and the program will start processing information in the background. You should only have to go through this process the first time you download from a given Canvas link (as the required information will be written to a cache file for future use).
    - NOTE: the program will automatically click "Call Me" on your default 2FA option. If you need to authenticate via a different number, cancel the default call, select the number you would prefer, and click "Call Me" manually. You have 120 seconds to finish the procedure before the script decides an error occurred and exits the program.


7. Wait for the program to finish. Often 30-50GB of data will need to be downloaded (and optionally uploaded). Depending on the strength of your internet connection, this process could take several of hours.
    - NOTE: I would highly suggest running your command of choice without the `--full` flag to make sure everything is working smoothly. You will need to delete the downloaded/uploaded local (and optinally S3) files before running the command *with* the `--full` flag (luigi can't tell a difference between `short` and `full` files).


### How does this work? What are the steps?

Before understanding how this program works, we should first ask "how would I download a file manually?" Because explaining this process in text/images would be a terrible expereince for all parties involved, I've recorded a video detailing how to manually download lectures. Here is the link: https://youtu.be/RqG7gyKWVeA

With the understanding that you've watched that video (8min) here's how this works:
1. The Google Chrome instance that this program starts has a special flag set such that is records all network traffic to a specific log file (found at `./data/tmp/net_log.json`). As noted in `step 6` of `setup`, the program will open all lecture links. As this is happening, it is recording all network actvity to the log file. After Chrome has been closed we can extract each lecture's m3u8 files from that network log. This is the same process we did by hand using the network tab of developer tools in the video above.


2. Once we have all of the base m3u8's we begin the long/tedious process of pairing m3u8s with their corresponding lecture and extracting the links that correspond to the highest resolution videos. Once we've extracted this data, we cache it (to a pkl file) so this process doesn't need to be repeated.


3. We download each lecture using the correct mp4 or ts files we've extracted. We can also download slides by way of a little clever HTML scraping if using the Panopto player (and requested by the user).


4. (if `upload` was requested) we upload each lecture to S3. We also upload each lecture's slide folder (if applicable)


**A little flow chart of the functions defined in `scrape.py`**
![](./imgs/function_flow_chart.jpg)
For more information see this brief walkthrough of the functions: https://youtu.be/WGDmAItHTM8


### A note on testing

As far as I am aware, it is not possible to test the web scraper in any reasonable way. It's so context dependent that I really don't see how much could be done...
The `SaveLectureData` luigi task makes very heavy use of the web scraper meaning it is equally untestable. The only potentially testable tasks are the Download/Upload Lecture/Slides. While it is not inconceivable that I test only these, it simply does not make sense in my mind to test such a small working segment on it's own.
