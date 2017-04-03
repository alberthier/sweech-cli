#!/usr/bin/env python

from __future__ import print_function

import codecs
import json
import os.path
import ssl
import sys

if sys.version > '3':
    from urllib.request import urlopen, Request, HTTPDigestAuthHandler, HTTPPasswordMgrWithDefaultRealm, build_opener, install_opener, HTTPError
    from urllib.parse import quote
else:
    from urllib2 import urlopen, quote, Request, HTTPDigestAuthHandler, HTTPPasswordMgrWithDefaultRealm, build_opener, install_opener, HTTPError


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


# == Sweech access ============================================================


class Connection(object):

    def __init__(self, base_url, log_function = None):
        self.base_url = base_url
        self._log_function = log_function


    # == Internal functions ===================================================


    def _log(self, msg):
        if self._log_function:
            self._log_function(msg)

    def _urlopen(self, path, postdata = None, headers = {}):
        return urlopen(Request(self.base_url + quote(path), data = postdata, headers = headers))


    def _fetch_json(self, path, postdata = None, headers = {}):
        response = self._urlopen(path, postdata, headers)
        content_type = response.info()['Content-Type']
        if content_type == 'application/json':
            content = response.read().decode('utf-8')
            return json.loads(content)
        else:
            raise RuntimeError('Not a JSON object')


    def _pull_recursive(self, path, destination, base_path = None):
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
                if not os.path.exists(localpath):
                    os.makedirs(os.path.join(destination, localpath))
                self._log(localpath + '/')
                for item in response['content']:
                    self._pull_recursive(path + '/' + item['name'], destination, base_path)
            else:
                response = self._urlopen('/api/fs' + path)
                self._log(localpath)
                with open(os.path.join(destination, localpath), 'wb') as f:
                    buffer_size = 64 * 1024
                    while True:
                        buffer = response.read(buffer_size)
                        f.write(buffer)
                        if len(buffer) != buffer_size:
                            break
        except HTTPError as err:
            raise RuntimeError("Unable to access to '{}'".format(path))


    def _push_recursive(self, path, destination, base_path = None):
        def upload_file(localpath, remotepath):
            size = os.stat(localpath).st_size
            if size != 0:
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
                    if remotepath[0] == '/':
                        remotepath = remotepath[1:]
                    if len(files) == 0 and len(dirs) == 0:
                        self._log('/' + remotepath + '/')
                        self.mkdir(remotepath)
                    else:
                        for filename in files:
                            upload_file(os.path.join(root, filename), '/' + remotepath + '/' + filename)
            else:
                upload_file(path, destination + '/' + os.path.split(path)[1])
        except HTTPError as err:
            raise RuntimeError("Unable to upload to '{}'\n".format(destination))


    # == Public API ===========================================================


    def info(self):
        return self._fetch_json('/api/info')


    def ls(self, path):
        try:
            response = self._fetch_json('/api/ls' + path)
            if 'content' in response:
                return response['content']
            else:
                return [ response ]
        except HTTPError as err:
            raise RuntimeError("Unable to access to '{}'".format(path))


    def mkdir(self, path):
        try:
            postdata = codecs.encode(json.dumps({ 'dir': path }), 'utf-8')
            self._urlopen('/api/fileops/mkdir', postdata).read()
        except HTTPError as err:
            raise RuntimeError("Unable to create '{}'".format(path))


    def rm(self, path):
        try:
            basedir, item = os.path.split(path)
            postdata = codecs.encode(json.dumps({ 'baseDir': basedir, 'items': [ item ] }), 'utf-8')
            self._urlopen('/api/fileops/delete', postdata).read()
        except HTTPError as err:
            raise RuntimeError("Unable to delete '{}'".format(path))


    def cat(self, path):
        try:
            return self._urlopen('/api/fs' + path)
        except HTTPError as err:
            raise RuntimeError("Unable to read '{}'".format(path))


    def pull(self, path, destination):
        self._pull_recursive(path, destination)
    

    def push(self, path, destination):
        self._push_recursive(path, destination)


# == CLI functions ============================================================


def _info(base_url):
    inf = Connection(base_url).info()
    print('Device:           {} {}'.format(inf['brand'], inf['model']))
    print('API:              {}'.format(inf['sdk']))
    print('Internal storage: {}'.format(inf['storagePaths']['internal']))
    external_storages = inf['storagePaths']['externals']
    for ext in external_storages:
        print('External storage: {}'.format(ext))
    directories = inf['directories']
    for dkey in sorted(directories.keys()):
        dinfo = directories[dkey]
        if dinfo['exists']:
            print('{:17} {}'.format(dkey[0].upper() + dkey[1:] + ':', dinfo['path']))


def _ls(base_url, paths):
    conn = Connection(base_url)
    for i, path in enumerate(paths):
        if len(paths) > 1:
            if i > 0:
                print('')
            print(path + ':')
        for item in conn.ls(path):
            print(_ls_item_to_str(item))


def _mkdir(base_url, paths):
    conn = Connection(base_url)
    for path in paths:
        conn.mkdir(path)


def _rm(base_url, paths):
    conn = Connection(base_url)
    for path in paths:
        conn.rm(path)


def _cat(base_url, paths):
    for path in paths:
        r = Connection(base_url).cat(path)
        buffer_size = 64 * 1024
        while True:
            buffer = r.read(buffer_size)
            os.write(1, buffer)
            if len(buffer) != buffer_size:
                break


def _pull(base_url, paths, destination):
    conn = Connection(base_url, print)
    for path in paths:
        conn.pull(path, destination)


def _push(base_url, paths, destination):
    conn = Connection(base_url, print)
    for path in paths:
        conn.push(path, destination)


# == Main =====================================================================


if __name__ == '__main__':
    testurl = 'http://192.168.0.77:4444'
    status = 1
    try:
        if sys.argv[1] == 'info':
            _info(testurl)
        elif sys.argv[1] == 'ls':
            _ls(testurl, sys.argv[2:])
        elif sys.argv[1] == 'pull':
            _pull(testurl, sys.argv[2:-1], sys.argv[-1])
        elif sys.argv[1] == 'push':
            _push(testurl, sys.argv[2:-1], sys.argv[-1])
        elif sys.argv[1] == 'mkdir':
            _mkdir(testurl, sys.argv[2:])
        elif sys.argv[1] == 'rm':
            _rm(testurl, sys.argv[2:])
        elif sys.argv[1] == 'cat':
            _cat(testurl, sys.argv[2:])
        sys.exit(0)
    except OSError as err:
        sys.stderr.write(str(err) + '\n')
        sys.exit(2)        
    except RuntimeError as err:
        sys.stderr.write(str(err.args[0]) + '\n')
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(3)
