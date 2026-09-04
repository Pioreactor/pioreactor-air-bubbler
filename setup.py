# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from setuptools import find_namespace_packages
from setuptools import setup


README = Path("README.md").read_text(encoding="utf-8")


setup(
    name="pioreactor-air-bubbler",
    version="0.12.0",
    license="MIT",
    description="Add an air bubbler to your Pioreactor as a background job",
    long_description=README,
    long_description_content_type="text/markdown",
    author_email="hello@pioreactor.com",
    author="Pioreactor",
    url="https://github.com/Pioreactor/pioreactor-air-bubbler",
    packages=find_namespace_packages(include=["pioreactor_air_bubbler*"]),
    include_package_data=True,
    python_requires=">=3.13",
    entry_points={"pioreactor.plugins": "pioreactor_air_bubbler = pioreactor_air_bubbler"},
)
