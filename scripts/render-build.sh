#!/usr/bin/env bash
set -euo pipefail

python -c 'import sys; assert sys.version_info[:2] == (3, 12), "Python 3.12가 필요합니다. Render의 PYTHON_VERSION 설정과 .python-version을 확인하세요."'
python -m pip install -r requirements.txt
python -m pip install 'https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl'
python -c 'import spacy; assert spacy.__version__ == "3.8.11"; assert spacy.load("en_core_web_sm").meta["version"] == "3.8.0"; print("Analysis engine and model verified")'
