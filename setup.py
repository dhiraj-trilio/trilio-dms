"""
Setup script for Trilio DMS
"""

from setuptools import setup, find_packages

with open('README.md', 'r') as f:
    long_description = f.read()

with open('requirements.txt', 'r') as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name='trilio-dms',
    version='1.0.0',
    description='Trilio Dynamic Mount Service',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Trilio Data',
    author_email='support@trilio.io',
    url='https://github.com/triliodata/trilio-dms',
    packages=find_packages(),
    install_requires=requirements,
    entry_points={
        'console_scripts': [
            'trilio-dms=trilio_dms.server.dms_server:main',
            'trilio-dms-cli=trilio_dms.cli.main:main',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
    ],
    python_requires='>=3.8',
)

