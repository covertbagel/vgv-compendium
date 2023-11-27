#!/bin/sh
# This needs to be run from w/i this directory.

gcloud config set project vgv-compendium
gcloud beta app deploy --no-cache app.yaml

