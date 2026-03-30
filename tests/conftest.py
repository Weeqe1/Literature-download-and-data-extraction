"""Pytest configuration and shared fixtures."""
import sys
import os

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etl_ensemble"))
