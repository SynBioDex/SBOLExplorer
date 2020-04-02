# SBOLExplorer

SBOLExplorer is a service that simplifies the process of analyzing and searching for parts within genetic design repositories.  For questions, contact Michael Zhang at <michael13162@gmail.com>

# Installation
1. These installation steps assume you have the latest version of SynBioHub up and running on http://localhost:7777.  For instructions, see https://github.com/SynBioHub/synbiohub.
2. Clone this repository with `git clone https://github.com/michael13162/SBOLExplorer.git`.
3. Install and run ElasticSearch 6.3 (https://www.elastic.co/guide/en/elasticsearch/reference/current/install-elasticsearch.html).
    * The exact steps will depend on your environment, so read the manual (aka RTFM).
    * Set up the package repo to install ElasticSearch from.
    * Install ElasticSearch.
    * Start ElasticSearch (will be different depending on init vs systemd).
    * Optionally, configure ElasticSearch to start on boot.
4. Install the latest version of Python 3 (https://www.python.org/downloads/).
5. Go to the SBOLExplorer/flask directory and run `pip install -r requirements.txt` to install all the dependencies.  Try `pip3` instead of `pip` if that doesn't work.
6. Run SBOLExplorer using `./start.sh` in the SBOLExplorer/flask directory.
7. To update the index for the first time, run `curl -X GET "localhost:13162/update"`.  Depending on repository size, this can take a couple of minutes.
8. Optionally, run `crontab update.cron` to automatically update SBOLExplorer periodically.
    * To change the update period, edit update.cron
9. In SynBioHub, go to the Admin->General page and specify `http://localhost:13162/` as the SBOLExplorer endpoint, check the `Searching Using SBOLExplorer` checkbox, and click `Save`.  Searches will now go through SBOLExplorer.

![alt text](https://raw.githubusercontent.com/michael13162/SBOLExplorer/master/visualization/network.png)

To run a neat visualization, go to the force_directed_graph folder and run "http-server" in the command line.  Then, open the browser to the hosted page.  Shown is a network visualization of part usage in SynBioHub.

# Automatic build and deploy
On each commit to master, a new Docker image is built and pushed to [Docker Hubhttps://hub.docker.com/r/michael13162/sbolexplore://hub.docker.com/r/michael13162/sbolexplorer). 
This is done by TravisCI.
The credentials used to push the image are stored in Travis. 
