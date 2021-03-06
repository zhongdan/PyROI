.. _config_file:

===============
The Config File
===============

The config file is central to PyROI.  Before you can do just about anything
else, you have to set up your config file, which tells the program which
atlases you want to use, how to use them, and where to find the data to
use them on.

Note to experienced Python users: this file does not actually take the
structure of typical Python "config" files.  Sorry if that is confusing.

Getting a config base
---------------------

To get a config file skeleton, start the python interpreter and run the 
following commands::

    >>> import pyroi as roi
    >>> roi.write_config_base("your_config_file_name")

Replace "your_config_file_name" with the name you wish to use, of course.
If you just give a file name, it will write the file to your working 
directory.  If you give it as a path, it will write the file to the
directory specified on the path.  If there is a file with the name you
give in the target directory, it will be overwritten, so make sure to 
check for that first.

There are two other options that can be given as arguments.  The 
function will attempt to write a file called .roiconfigfile to the
target directory, the contents of which will tell PyROI the name of
your config file.  If this file exists when you run the ``write_config_base``
function, however, it will not be overwritten.  You can cause the file 
to be overwritten by adding the argument ``force = True`` to the function
call.

All of the file paths in PyROI are absolute, so the location of your
config file has no special relation to the location of your data.  If 
multiple config files will be associated with the same dataset, it is
advisable to keep them in separate directories, so as to take advantage
of the automatic importing of the config file, which can only happen
for one file per directory.

By default, the config file base contains a lot of commentary on what
the different parts of the config file do and the format they are
expected to be in.  If you want to write a clean config file without
all of these coments, add the argument ``clean = True`` to the function
call.  This is not recommended for beginners.

Config file content
-------------------

.. include:: config_doc.rst

