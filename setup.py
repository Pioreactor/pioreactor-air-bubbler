# -*- coding: utf-8 -*-
from setuptools import setup

with open("requirements/requirements.txt") as f:
    REQUIREMENTS = f.read().splitlines()


setup(
    name="pioreactor_bubbler",
    version="0.0.5",
    license="MIT",
    install_requires=REQUIREMENTS,
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author_email="cam@pioreactor.com",
    entry_points={"pioreactor.plugins": "pioreactor_bubbler = pioreactor_bubbler"},
)
