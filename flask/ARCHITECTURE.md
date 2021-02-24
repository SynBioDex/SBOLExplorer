# Overview of SBOLExplorer's Architecture

## Start.sh
Run this bash script to start an instance of SBOLExplorer at http://localhost:3000

## Explorer.py
This is the main file of SBOLExplorer. All endpoints and Flask configuration are handled through this file.

## Index.py
This file contains all the methods needed for indexing. ``update_index()`` is the main method where all other helper methods are called.

## Pagerank.py
The "core" of SBOLExplorer. This is where the pagerank algorithm used in indexing is contained.

## Query.py
When indexing, SBOLExplorer uses these methods to query both Elasticseasrch and SPARQL for parts.

## Search.py
All of the processing of search terms goes here. Explorer decides where to send the search query based on the parameters of the search.

## Sequencesearch.py
This adds support for sequence-based searching via SBOLExplorer. 
This is done using a VSEARCH binary located in the /usearch/ folder 
(note that USEARCH binaries are also available, but currently are not supported for sequence-based searching).

## Utils.py
Methods for getting the config file, any necessary external endpoints, or serializing/deserializing files are located here.
