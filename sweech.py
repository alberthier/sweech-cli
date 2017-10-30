#!/usr/bin/env python

from __future__ import print_function

import argparse
import codecs
import json
import os.path
import ssl
import sys
import types

if sys.version > '3':
    from urllib.parse import quote
    from urllib.request import build_opener, urlopen, urlparse, AbstractDigestAuthHandler, \
                               HTTPDigestAuthHandler, HTTPError, HTTPPasswordMgrWithDefaultRealm, \
                               HTTPSHandler, Request, URLError
else:
    from urllib2 import quote, build_opener, urlopen, urlparse, AbstractDigestAuthHandler, \
                               HTTPDigestAuthHandler, HTTPError, HTTPPasswordMgrWithDefaultRealm, \
                               HTTPSHandler, Request, URLError


# == Internal helper functions ================================================


def _ls_item_to_str(item):
    isDir = item['isDir']
    line = 'd' if isDir else '-'
    line += 'r' if item['isReadable'] else '-'
    line += 'w' if item['isWritable'] else '-'
    line += '    '
    line += '{:>7}'.format(item['size']) if isDir else _pretty_size(item['size'])
    line += '    '
    line += item['name']
    if isDir:
        line += '/'
    return line


def _pretty_size(size):
    if size < 1024:
        return '{:>7}'.format(size)
    elif size < 1024 * 1024:
        return '{:>6.1f}K'.format(size / 1024.0)
    elif size < 1024 * 1024 * 1024:
        return '{:>6.1f}M'.format(size / (1024.0 * 1024.0))
    else:
        return '{:>6.1f}G'.format(size / (1024.0 * 1024.0 * 1024.0))


def _make_abs(args, path):
    if not path.startswith('/') and hasattr(args, 'defaultdir'):
        return args.defaultdir + '/' + path
    return path


class HTTPSDigestAuthHandler(HTTPSHandler, AbstractDigestAuthHandler):

    def __init__(self, passwordmgr, context):
        HTTPSHandler.__init__(self, context = context)
        AbstractDigestAuthHandler.__init__(self, passwordmgr)

    auth_header = 'Authorization'
    handler_order = 490  # before Basic auth

    def http_error_401(self, req, fp, code, msg, headers):
        host = urlparse(req.full_url)[1]
        retry = self.http_error_auth_reqed('www-authenticate', host, req, headers)
        self.reset_retry_count()
        return retry


# == Sweech access ============================================================


class Connector(object):
    """A Connector is used to access to an Android device running Sweech"""

    def __init__(self, base_url, user = None, password = None, log_function = None):
        """
        Args:
            base_url (str): the URL displayed in the Sweech app (ex: 'http://192.168.0.65:4444')
            user (str, optional): the username if login is enabled in the app
            password (str, optional): the password if login is enabled in the app
            log_function (function): a function to be called to log runtime information
        """
        self.base_url = base_url
        self._log_function = log_function
        passwordmgr = HTTPPasswordMgrWithDefaultRealm()
        passwordmgr.add_password('Sweech', base_url, user, password)
        auth_handler = HTTPDigestAuthHandler(passwordmgr)
        https_auth_handler = HTTPSDigestAuthHandler(passwordmgr, ssl.SSLContext(ssl.PROTOCOL_SSLv23))
        self._opener = build_opener(auth_handler, https_auth_handler)


    # == Internal functions ===================================================


    def _log(self, msg):
        if self._log_function:
            self._log_function(msg)

    def _urlopen(self, path, postdata = None, headers = {}):
        return self._opener.open(Request(self.base_url + quote(path), data = postdata, headers = headers))


    def _fetch_json(self, path, postdata = None, headers = {}):
        response = self._urlopen(path, postdata, headers)
        content_type = response.info()['Content-Type']
        if content_type == 'application/json':
            content = response.read().decode('utf-8')
            return json.loads(content)
        else:
            raise RuntimeError('Not a JSON object')


    def _pull_recursive(self, path, destination, keep, base_path = None):
        try:
            response = self._fetch_json('/api/ls' + path)
        except HTTPError as err:
            raise RuntimeError("Unable to access to '{}'".format(path))
        try:
            if base_path is None:
                base_path = os.path.split(path)[0]
            localpath = path[len(base_path):]
            if localpath[0] == '/':
                localpath = localpath[1:]
            if response['isDir']:
                local_dir_path = os.path.join(destination, localpath)
                if not os.path.exists(local_dir_path):
                    self._log(localpath + '/')
                    os.makedirs(local_dir_path)
                for item in response['content']:
                    self._pull_recursive(path + '/' + item['name'], destination, keep, base_path)
            else:
                local_file_path = os.path.join(destination, localpath)
                if not keep or not os.path.exists(local_file_path):
                    response = self._urlopen('/api/fs' + path)
                    self._log(localpath)
                    with open(local_file_path, 'wb') as f:
                        buffer_size = 64 * 1024
                        while True:
                            buffer = response.read(buffer_size)
                            f.write(buffer)
                            if len(buffer) != buffer_size:
                                break
        except HTTPError as err:
            raise RuntimeError("Unable to access to '{}'".format(path))


    def _push_recursive(self, path, destination, keep, base_path = None):
        def upload_file(localpath, remotepath):
            size = os.stat(localpath).st_size
            with open(localpath, 'rb') as f:
                self._log(remotepath)
                self._urlopen('/api/fs' + remotepath, f, { 'Content-Length': size }).read()

        try:
            path = os.path.abspath(path)
            if os.path.isdir(path):
                if base_path is None:
                    base_path = os.path.split(path)[0]
                for root, dirs, files in os.walk(path):
                    remotepath = destination + root[len(base_path):]
                    content = []
                    remote_dir_exists = False
                    if keep:
                        try:
                            content = list(map(lambda item: item['name'], self.ls(remotepath)))
                            remote_dir_exists = True
                        except:
                            pass
                    if remotepath[0] == '/':
                        remotepath = remotepath[1:]
                    if len(files) == 0 and len(dirs) == 0 and not remote_dir_exists:
                        self._log('/' + remotepath + '/')
                        self.mkdir(remotepath)
                    else:
                        for filename in files:
                            if not filename in content:
                                upload_file(os.path.join(root, filename), '/' + remotepath + '/' + filename)
            else:
                remote_file_exists = False
                dest_path = destination + '/' + os.path.split(path)[1]
                if keep:
                    try:
                        self.ls(dest_path)
                    except:
                        remote_file_exists = True
                if not keep or remote_file_exists:
                    upload_file(path, dest_path)
        except HTTPError as err:
            raise RuntimeError("Unable to upload to '{}'\n".format(destination))


    # == Public API ===========================================================


    def info(self):
        """Returns a dict with information on the device (name, paths, ...)"""
        return self._fetch_json('/api/info')


    def ls(self, path):
        """Returns a list of dics with information on a filesystem entry"""
        try:
            response = self._fetch_json('/api/ls' + path)
            if 'content' in response:
                return response['content']
            else:
                return [ response ]
        except HTTPError as err:
            raise RuntimeError("Unable to access to '{}'".format(path))


    def mkdir(self, path):
        """Creates a new directory.
        Missing intermediate paths are created.
        """
        try:
            postdata = codecs.encode(json.dumps({ 'dir': path }), 'utf-8')
            self._urlopen('/api/fileops/mkdir', postdata).read()
        except HTTPError as err:
            raise RuntimeError("Unable to create '{}'".format(path))


    def rm(self, path):
        """Deletes a file or diectory
        If path is a direcrory, its content is recursively deleted
        """
        try:
            basedir, item = os.path.split(path)
            postdata = codecs.encode(json.dumps({ 'baseDir': basedir, 'items': [ item ] }), 'utf-8')
            self._urlopen('/api/fileops/delete', postdata).read()
        except HTTPError as err:
            raise RuntimeError("Unable to delete '{}'".format(path))


    def mv(self, src_path, dst_path):
        """Move a file or directory
        Moving files between directories may be slow if src_path and dst_path aren't on the same volume.
        In this case, a copy + delete is done.
        """
        try:
            postdata = codecs.encode(json.dumps({ 'src': src_path, 'dst': dst_path }), 'utf-8')
            self._urlopen('/api/fileops/move', postdata).read()
        except HTTPError as err:
            raise RuntimeError("Unable to move '{}' to '{}'".format(src_path, dst_path))


    def cat(self, path):
        """Returns a file-like object with the content of the file at path"""
        try:
            return self._urlopen('/api/fs' + path)
        except HTTPError as err:
            raise RuntimeError("Unable to read '{}'".format(path))


    def pull(self, path, destination, keep = True):
        """Copies a file or directory from the device to the local path

        Args:
            path (str): Absolute remote path of a file or directory to download
            destination (str): Local destination path
            keep (bool): if true, existing local files are preserved
        """
        self._pull_recursive(path, destination, keep)


    def push(self, path, destination, keep = True):
        """Copies a file or directory to the device

        Args:
            path (str): Local path of a file or directory to upload
            destination (str): Absolute remote destination path
            keep (bool): if true, existing remote files are preserved
        """
        self._push_recursive(path, destination, keep)


    def clipboard(self, text = None):
        """ Gets or sets the clipboard content

        Args:
            text (str): The text to put in the Android clipboard
            or None to get the clipboard content
        """
        if text == None:
            response = self._fetch_json('/api/clipboard')
            return response['content']
        else:
            postdata = codecs.encode(json.dumps({ 'content': text }), 'utf-8')
            self._urlopen('/api/clipboard', postdata).read()


# == CLI functions ============================================================


def _info(args):

    def print_storage_info(storage):
        print('  Path:           {}'.format(storage['path']))
        name = storage['name']
        if name is not None:
            print('  Name:           {}'.format(name))
        print('  Available:    {}'.format(_pretty_size(storage['availableBytes'])))
        print('  Total:        {}'.format(_pretty_size(storage['totalBytes'])))

    inf = Connector(args.url, args.user, args.password).info()
    print('Device:           {} {}'.format(inf['brand'], inf['model']))
    print('API:              {}'.format(inf['sdk']))
    print('Internal storage:')
    print_storage_info(inf['storagePaths']['internal'])
    external_storages = inf['storagePaths']['externals']
    if len(external_storages) > 0:
        print('External storage:')
        for i, ext in enumerate(external_storages):
            if i > 0:
                print()
            print_storage_info(ext)
    directories = inf['directories']
    for dkey in sorted(directories.keys()):
        dinfo = directories[dkey]
        if dinfo['exists']:
            print('{:17} {}'.format(dkey[0].upper() + dkey[1:] + ':', dinfo['path']))


def _ls(args):
    if len(args.paths) == 0:
        if hasattr(args, 'defaultdir'):
            args.paths.append(args.defaultdir)
        else:
            raise RuntimeError('Path missing')
    conn = Connector(args.url, args.user, args.password)
    for i, path in enumerate(args.paths):
        path = _make_abs(args, path)
        if len(args.paths) > 1:
            if i > 0:
                print('')
            print(path + ':')
        for item in conn.ls(path):
            print(_ls_item_to_str(item))


def _mkdir(args):
    conn = Connector(args.url, args.user, args.password)
    for path in args.paths:
        conn.mkdir(_make_abs(args, path))


def _rm(args):
    conn = Connector(args.url, args.user, args.password)
    for path in args.paths:
        conn.rm(_make_abs(args, path))


def _mv(args):
    # Fix destination as argparse cannot handle both '*' and '?' arguments
    if len(args.paths) > 1:
        args.destination = args.paths.pop()
    else:
        raise RuntimeError('Destination path missing')
    conn = Connector(args.url, args.user, args.password)
    dst = _make_abs(args, args.destination)
    for path in args.paths:
        conn.mv(_make_abs(args, path), dst)


def _cat(args):
    conn = Connector(args.url, args.user, args.password)
    for path in args.paths:
        r = conn.cat(_make_abs(args, path))
        buffer_size = 64 * 1024
        while True:
            buffer = r.read(buffer_size)
            os.write(1, buffer)
            if len(buffer) != buffer_size:
                break


def _pull(args):
    # Fix destination as argparse cannot handle both '*' and '?' arguments
    args.destination = args.paths.pop() if len(args.paths) > 1 else '.'
    conn = Connector(args.url, args.user, args.password, print)
    for path in args.paths:
        conn.pull(_make_abs(args, path), args.destination, args.keep)


def _push(args):
    # Fix destination as argparse cannot handle both '*' and '?' arguments
    if len(args.paths) > 1:
        args.destination = args.paths.pop()
    else:
        if hasattr(args, 'defaultdir'):
            args.destination = args.defaultdir
        else:
            raise RuntimeError('Destination path missing')
    conn = Connector(args.url, args.user, args.password, print)
    for path in args.paths:
        conn.push(path, _make_abs(args, args.destination), args.keep)


def _clipboard(args):
    result = Connector(args.url, args.user, args.password).clipboard(args.text)
    if result is not None:
        print(result)


# == Main =====================================================================


def _main():
    main_parser = argparse.ArgumentParser(description = 'Sweech command line')
    main_parser.add_argument('-u', '--url', help = 'URL displayed in the Sweech app')
    main_parser.add_argument('--user', help = 'Username if a password has been set')
    main_parser.add_argument('--password', help = 'Password if a password has been set')

    subparsers = main_parser.add_subparsers(dest = 'command', title='Available commands', metavar = 'command')

    subparsers.add_parser('info', help = 'Prints information and default paths of your device')

    subparser = subparsers.add_parser('ls', help = 'List the content of a folder or display details of a file')
    subparser.add_argument('paths', nargs = '*', help = 'Paths to list')

    subparser = subparsers.add_parser('pull', help = 'Pull files and folders from the remote device to a local folder',
                                              description="""Pull files and folders from the remote device to a local folder.
                                                             If remote file path is relative, the `defaultdir` entry in
                                                             `settings.json` is used as base""")
    subparser.add_argument('--keep', help = 'Preserve existing files', action = 'store_true')
    subparser.add_argument('paths', nargs = '+', help = 'Remote paths to pull')
    subparser.add_argument('destination', nargs = '?', help = 'Local destination path')

    subparser = subparsers.add_parser('push', help = "Pushes files or directories to a remote path.",
                                              description="""Pushes files or directories to a remote path.
                                                             If no remote file is specified or a relative path is used,
                                                             the `defaultdir` entry in `settings.json` is used as base.
                                                             You can only create files and folders in the internal storage.
                                                             External storage (SD card) is writable too if you have granted
                                                             Sweech this authorisation in the app's settings.""")    
    subparser.add_argument('--keep', help = 'Preserve existing files', action = 'store_true')
    subparser.add_argument('paths', nargs = '+', help = 'Local paths to push')
    subparser.add_argument('destination', nargs = '?', help = 'Remote destination path')

    subparser = subparsers.add_parser('mkdir', help = 'Create remote folders',
                                               description="Create remote folders. Missing intermediate directories are created too")
    subparser.add_argument('paths', nargs = '+', help = 'Folders to create')

    subparser = subparsers.add_parser('rm', help = 'Delete remote files and folders')
    subparser.add_argument('paths', nargs = '+', help = 'Files and folders to delete')

    subparser = subparsers.add_parser('mv', help = 'Move remote files and folders')
    subparser.add_argument('paths', nargs = '+', help = 'Paths to move')
    subparser.add_argument('destination', nargs = '?', help = 'Destination path')

    subparser = subparsers.add_parser('cat', help = 'Displays the content of files')
    subparser.add_argument('paths', nargs = '+', help = 'Files to display')

    subparser = subparsers.add_parser('clipboard', help = 'Get or set the clipboard content')
    subparser.add_argument('text', nargs = '?', help = 'The text to put in the clipboard or omit to get the clipboard content')

    args = main_parser.parse_args()

    if args.command is None:
        main_parser.print_help()
        sys.exit(1)

    config = {}
    if sys.platform == 'win32':
        config_path = os.path.join(os.getenv('APPDATA'), 'sweech.json')
    else:
        config_path = os.path.join(os.getenv('HOME'), '.config', 'sweech.json')
    if os.path.exists(config_path):
        config = json.loads(open(config_path).read())
    for key in config.keys():
        if not hasattr(args, key) or getattr(args, key) is None:
            setattr(args, key, config[key])

    try:
        handler = getattr(sys.modules[__name__], '_' + args.command)
        if handler:
            handler(args)
        sys.exit(0)
    except URLError as err:
        sys.stderr.write(str(err.reason) + '\n')
        sys.exit(2)
    except OSError as err:
        sys.stderr.write(str(err) + '\n')
        sys.exit(2)
    except RuntimeError as err:
        sys.stderr.write(str(err.args[0]) + '\n')
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(3)


if __name__ == '__main__':
    _main()