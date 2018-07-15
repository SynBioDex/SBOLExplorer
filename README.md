# SBOLExplorer

SBOLExplorer is a service that simplifies the process of analyzing and searching for parts within genetic design repositories.  For questions, contact Michael Zhang at <michael13162@gmail.com>

# Installation
1. These installation steps assume you have the latest version of SynBioHub up and running on http://localhost:7777.  For instructions, see https://github.com/SynBioHub/synbiohub.
2. Clone this repository with `git clone https://github.com/michael13162/SBOLExplorer.git`.
3. Install and run ElasticSearch 6.3 (https://www.elastic.co/guide/en/elasticsearch/reference/current/install-elasticsearch.html).
4. Install the latest version of Python 3 (https://www.python.org/downloads/).
5. Go to the SBOLExplorer/flask directory and run `pip install -r requirements.txt` to install all the dependencies.
6. Run SBOLExplorer using `./start.sh` in the SBOLExplorer/flask directory.
7. In SynBioHub, go to the Admin->General page and specify http://localhost:13162/ as the SBOLExplorer endpoint, check the `Searching Using SBOLExplorer` checkbox, and click `Save`.  Searches will now go through SBOLExplorer.

# Phase 0: Visualization

![alt text](https://raw.githubusercontent.com/michael13162/SBOLExplorer/master/visualization/network.png)

To run a neat visualization, go to the force_directed_graph folder and run "http-server" in the command line.  Then, open the browser to the hosted page.  Shown is a network visualization of part usage in SynBioHub.

# Phase 1: Clustering

Clustering is useful for merging duplicate or near duplicate parts in a repository.  This makes sense since many biological parts are just variations of each other.

First, we preprocess the sequence data and generate an initial cumulative density plot of sequence pair similarity using Jaccard distance.

![alt text](https://raw.githubusercontent.com/michael13162/SBOLExplorer/master/figs/unnormalized_base_frequencies.png)
![alt text](https://raw.githubusercontent.com/michael13162/SBOLExplorer/master/figs/base_frequencies.png)

Hierarchical single link clustering profile results are not good... projected 27 years

![alt text](https://raw.githubusercontent.com/michael13162/SBOLExplorer/master/figs/profile_results.png)

Using a disjoint set and streaming over all pairs of sequences is faster and also results in single link clustering.

![alt text](https://raw.githubusercontent.com/michael13162/SBOLExplorer/master/figs/clustering_slide.jpg)

# Phase 2: Ranking

Clusters of parts represent a single biological part.  Different parts have different degrees of usefullness, just like different websites on the internet have different popularities.

PageRank and analyzing the Markov chain model can help us understand a part's intrinsic "usefulness".  *Figures from http://www.cs.utah.edu/~jeffp/teaching/cs5140.html*

![alt text](https://raw.githubusercontent.com/michael13162/SBOLExplorer/master/figs/ranking_slide.jpg)


# Phase 3: Indexing

An inverted index (ElasticSearch) can be used to quickly go from query input to list of parts sorted by rank.

![alt text](https://raw.githubusercontent.com/michael13162/SBOLExplorer/master/figs/indexing_slide.jpg)

# Workflow

The end result should be integrated back into SynBioHub's search functionality and APIs.  Other tools in the SBOL workflow can then benefit from an easier way to find parts.

![alt text](https://raw.githubusercontent.com/michael13162/SBOLExplorer/master/figs/workflow_slide.jpg)
