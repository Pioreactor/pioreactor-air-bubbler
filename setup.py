# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

with open("requirements/requirements.txt") as f:
    REQUIREMENTS = f.read().splitlines()


setup(
    name="pioreactor_airpump",
    version="0.0.2",
    license="MIT",
    long_description=open("README.md").read(),
    packages=find_packages(exclude=["*.tests", "*.tests.*"]),
    author_email="cam@pioreactor.com",
    entry_points={'pioreactor.plugins': 'pioreactor_airpump = pioreactor_airpump'},
)
