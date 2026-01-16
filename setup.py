"""
Setup configuration for Trilio DMS
"""

from setuptools import setup, find_packages
import os

# Read README
def read_file(filename):
    with open(os.path.join(os.path.dirname(__file__), filename), encoding='utf-8') as f:
        return f.read()

setup(
    name='trilio-dms',
    version='1.0.0',
    description='Trilio Dynamic Mount Service - Centralized mount/unmount service for backup targets',
    long_description=read_file('README.md'),
    long_description_content_type='text/markdown',
    author='Trilio',
    author_email='support@trilio.io',
    url='https://github.com/dhiraj-trilio/trilio-dms',
    license='Apache License 2.0',
    
    packages=find_packages(exclude=['tests', 'tests.*', 'examples', 'examples.*']),
    
    install_requires=[
        'pika>=1.3.2',
        'sqlalchemy>=1.4.48',
        'pymysql>=1.0.3',
        'requests>=2.31.0',
        'click>=8.1.3',
        'tabulate>=0.9.0',
        'python-dateutil>=2.8.2',
        'python-json-logger>=2.0.7',
    ],
    
    extras_require={
        'dev': [
            'pytest>=7.4.0',
            'pytest-cov>=4.1.0',
            'pytest-mock>=3.11.1',
            'mock>=5.1.0',
            'black>=23.7.0',
            'flake8>=6.1.0',
            'mypy>=1.4.1',
        ],
        'prod': [
            'gunicorn>=21.2.0',
            'supervisor>=4.2.5',
        ],
    },
    
    entry_points={
        'console_scripts': [
            'trilio-dms-server=trilio_dms.server:main',
            'trilio-dms-cli=trilio_dms.cli:cli',
        ],
    },
    
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: System :: Archiving :: Backup',
        'Topic :: System :: Systems Administration',
    ],
    
    python_requires='>=3.8',
    
    include_package_data=True,
    zip_safe=False,
    
    keywords='backup mount nfs s3 trilio storage',
    
    project_urls={
        'Bug Reports': 'https://github.com/dhiraj-trilio/trilio-dms/issues',
        'Source': 'https://github.com/dhiraj-trilio/trilio-dms',
        'Documentation': 'https://github.com/dhiraj-trilio/trilio-dms#readme',
    },
)
