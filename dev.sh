#!/bin/sh
# This needs to be run from w/i this directory.
# Do `gcloud auth application-default login` to fix "invalid_grant" errors

# `--application=` must be changed to match your own project name!
# TODO: Configure `--application=` outside of git?

# This ends up using the "production" datastore, so need to be careful
# not to mess things up too much!
# TODO: Figure out how to have a separate "dev" datastore?

dev_appserver.py --application=vgv-compendium --runtime_python_path=/usr/bin/python3 app.yaml

