#!/bin/bash
# TODO flesh out script to launch/start/set everything up

echo "Starting SBOLExplorer"

export FLASK_APP=explorer.py
export FLASK_ENV=development
flask run --host=0.0.0.0 --port=13162
