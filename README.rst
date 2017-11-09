Sweech command line interface
=============================

What's this ?
-------------

It's a command line tool to interact with `Sweech Wifi file transfer <https://play.google.com/store/apps/details?id=com.sweech>`_.

Sweech is an Android app with which you can browse the content of your phone and transfer files. It's based on an HTTP server. This tool interacts with Sweech's HTTP API. You can push and pull files over wifi directly from your favorite shell

OK, show me !
-------------

.. image:: https://asciinema.org/a/113791.png
    :target: https://asciinema.org/a/113791?speed=2

Nice, how do I get it ?
-----------------------

Use python's ``pip``

.. code::

    $ pip install sweech-cli

Or download the python script and add it to your ``$PATH``

.. code::

    $ curl -o sweech https://raw.githubusercontent.com/alberthier/sweech-cli/master/sweech.py

Or

.. code::

    $ wget -O sweech https://raw.githubusercontent.com/alberthier/sweech-cli/master/sweech.py

How do I use it ?
-----------------

The ``sweech`` tool is totally standalone:

.. code::

    $ sweech -u http://192.168.0.65 info


It may be practical to create a config file containing the connection settings: ``~/.config/sweech.json`` on Linux/macOS, ``%APPDATA%/sweech.json`` on Windows

Here is an example file for a phone having ``192.168.0.65`` as IP address

.. code:: json

    {
        "url": "http://192.168.0.65:4444",
        "user": "",
        "password": "",
        "defaultdir": "/storage/emulated/0/Downloads"
    }

If you define a ``defaultdir``, all relative remote paths will be interpreted relatively to this default directory.

Assuming you have added ``sweech`` to your ``PATH``:

.. code::

    $ sweech info

Prints information and default paths of your device

.. code::

    $ sweech ls /storage/emulated/0/Download

List the content of a folder or display details of a file

.. code::
    
    $ sweech push testdir

Pushes files or directories to a remote path. If no remote file is specified, ``defaultdir`` is used

You can only create files and directories in the internal storage. External storage (SD card) is writable too if you have granted Sweech this authorisation in the app's settings.

The ``--keep`` option uploads only missing files on the remote device. Existing files are left untouched.

.. code::

    $ sweech pull testdir

Pull files and folders from the remote device to a local folder. If remote file path is relative, ``defaultdir`` is used as base

The ``--keep`` option downloads only missing local files. Existing files are left untouched.

.. code::

    $ sweech mkdir testdir

Creates a directory. Missing intermediate directories are created too

.. code::

    $ sweech rm /some/path

Removes a file or a directory (with its content)

.. code::

    $ sweech mv /some/path /some/otherpath

Moves a file or a directory (with its content). Moving files between directories may be slow in some circumstances (between different storages, on external SD card on Android pre 7.0)

.. code::

    $ sweech cat /path/to/some/file.txt

Displays the content of a file

.. code::

    $ sweech clipboard

Displays the content of the Android clipboard

.. code::

    $ sweech clipboard "Hello World"

Sets the content of the Android clipboard

And what if I want to use it in my Python script ?
--------------------------------------------------

Simply import the ``sweech`` module and use the ``Connector`` object. All CLI commands have their equivalent method:

.. code:: python

    import sweech

    c = sweech.Connector('http://192.168.0.11:4444')

    print(c.info())

    for f in c.ls('/storage/emulated/0/Download'):
        print(f)

    with open('test.txt', 'wt') as f:
        f.write('Hello World')

    c.push('test.txt', '/storage/emulated/0/Download')

    c.pull('/storage/emulated/0/Download/test.txt', '/tmp')

    f = c.cat('/storage/emulated/0/Download/test.txt')
    print(f.read().decode('utf-8'))
    f.close()

    c.mkdir('/storage/emulated/0/Download/testdir')

    c.mv('/storage/emulated/0/Download/testdir', '/storage/emulated/0/Download/testdir2')

    c.rm('/storage/emulated/0/Download/testdir2')

    txt = c.clipboard()
    c.clipboard(txt + " hello world")

Dependencies
------------

* Python 2.7 or Python 3.5+

Contributing
------------

Report issues `here <https://github.com/alberthier/sweech-cli/issues>`_

Pull-requests welcome !