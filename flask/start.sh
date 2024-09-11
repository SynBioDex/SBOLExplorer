#!/bin/bash

echo "Starting SBOLExplorer"
source ../../jammy/bin/activate
export FLASK_APP=explorer.py
export FLASK_ENV=development
flask run --host=0.0.0.0 --port=13162
