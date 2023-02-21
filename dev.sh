#!/bin/sh
# This needs to be run from w/i this directory.

# GOOGLE_CLOUD_PROJECT must be changed to match your own project name!
# TODO: Configure GOOGLE_CLOUD_PROJECT outside of git?

# This ends up using the "production" datastore, so need to be careful
# not to mess things up too much!
# TODO: Figure out how to have a separate "dev" datastore?

GOOGLE_CLOUD_PROJECT=vgv-compendium dev_appserver.py app.yaml

