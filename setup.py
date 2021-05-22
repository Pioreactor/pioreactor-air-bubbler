# -*- coding: utf-8 -*-
from setuptools import setup

with open("requirements/requirements.txt") as f:
    REQUIREMENTS = f.read().splitlines()


setup(
    name="pioreactor_bubbler",
    version="0.0.4",
    license="MIT",
    install_requires=REQUIREMENTS,
    long_description=open("README.md").read(),
    author_email="cam@pioreactor.com",
    entry_points={"pioreactor.plugins": "pioreactor_bubbler = pioreactor_bubbler"},
)
