from setuptools import setup

def read(fname):
    import os
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = "sweech-cli",
    version = "1.1.0",
    description = "A command-line utility to interact with your Android device through the Sweech app",
    long_description = read('README.rst'),
    url = 'https://github.com/alberthier/sweech-cli',
    license = 'MIT',
    author = 'Eric ALBER',
    author_email = 'eric.alber@gmail.com',
    classifiers = [
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
    ],
    py_modules = ['sweech'],
    entry_points = {
        'console_scripts': [
            'sweech = sweech:_main',
        ]
    }
)
