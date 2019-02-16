#!/bin/bash

# Run pycodestyle checks
pycodestyle ./source

# Run pylint checks
pylint `find ./source -type f -name '*.py' ! -name 'build_man.py'` --msg-template='{path}:{line}: [{msg_id}({symbol}), {obj}] {msg}' --rcfile ./setup.cfg
