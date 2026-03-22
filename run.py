#!/usr/bin/env python3
"""Quick launcher - run from project root: python run.py"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from eve_goggles.main import main
main()
