import os
from setuptools import setup, find_packages
import warnings

setup(
    name='cloud-compose-ecs',
    version='0.1.0',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'click>=6.6',
        'boto3>=1.3.1',
        'cloud-compose>=0.4.0',
        'cloud-compose-cluster>=0.14.0'
    ],
    setup_requires=[
        'pytest-runner'
    ],
    tests_require=[
        'pytest',
    ],
    namespace_packages = ['cloudcompose'],
    author="WaPo platform tools team",
    author_email="opensource@washingtonpost.com",
    url="https://github.com/cloud-compose/cloud-compose-ecs",
    download_url = "https://github.com/cloud-compose/cloud-compose-ecs/tarball/v0.1.0",
    keywords = ['ecs', 'cloud', 'compose', 'aws'],
    classifiers = []
)
