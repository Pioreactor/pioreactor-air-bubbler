# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

with open("requirements/requirements.txt") as f:
    REQUIREMENTS = f.read().splitlines()


setup(
    name="pioreactor_air_bubbler",
    version="0.0.3",
    license="MIT",
    install_requires=REQUIREMENTS,
    description="Add aa air bubbler to your Pioreactor as a background job",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author_email="cam@pioreactor.com",
    author="Cam Davidson Pilon",
    url="https://github.com/Pioreactor/pioreactor-air-bubbler",
    packages=find_packages(),
    include_package_data=True,
    entry_points={
        "pioreactor.plugins": "pioreactor_air_bubbler = pioreactor_air_bubbler"
    },
)
