#!/bin/bash

# Navigate to your SampleDatabase project directory
cd ~/Desktop/SampleDatabase || exit 1

# Activate the virtual environment
source venv/bin/activate

# Pull the latest version from the 'main' branch
git pull origin main

# (Optional) Deactivate the virtual environment if you don’t need to stay in it
# deactivate
