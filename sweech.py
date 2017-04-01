#!/usr/bin/env python

from __future__ import print_function

import codecs
import json
import os.path
import ssl
import sys

if sys.version > '3':
    from urllib.request import urlopen, Request, HTTPError
    from urllib.parse import quote
else:
    from urllib2 import urlopen, quote, Request, HTTPError


# == Internal helper functions ================================================


def _urlopen(*args, **kwargs):
    kwargs['context'] = ssl.SSLContext(ssl.PROTOCOL_TLS)
    return urlopen(*args, **kwargs)


def _fetch_json(url, postdata = None):
    response = _urlopen(url, postdata)
    content_type = response.info()['Content-Type']
    if content_type == 'application/json':
        content = response.read().decode('utf-8')
        return json.loads(content)
    else:
        raise RuntimeError('Not a JSON object')


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


def _pull_recursive(baseurl, path, destination, log = None, base_path = None):
    try:
        response = _fetch_json(baseurl + '/api/ls' + quote(path))
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
            if log is not None:
                log(localpath + '/')
            for item in response['content']:
                _pull_recursive(baseurl, path + '/' + item['name'], destination, log, base_path)
        else:
            response = _urlopen(baseurl + '/api/fs' + quote(path))
            if log is not None:
                log(localpath)
            with open(os.path.join(destination, localpath), 'wb') as f:
                buffer_size = 64 * 1024
                while True:
                    buffer = response.read(buffer_size)
                    f.write(buffer)
                    if len(buffer) != buffer_size:
                        break
    except HTTPError as err:
        raise RuntimeError("Unable to access to '{}'".format(path))


def _push_recursive(baseurl, path, destination, log = None, base_path = None):
    def upload_file(localpath, remotepath):
        size = os.stat(localpath).st_size
        if size != 0:
            with open(localpath, 'rb') as f:
                url = baseurl + '/api/fs' + quote(remotepath)
                log(remotepath)
                _urlopen(Request(url, data = f, headers = { 'Content-Length': size })).read()

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
                    log('/' + remotepath + '/')
                    mkdir(baseurl, remotepath)
                else:
                    for filename in files:
                        upload_file(os.path.join(root, filename), '/' + remotepath + '/' + filename)
        else:
            upload_file(path, destination + '/' + os.path.split(path)[1])
    except HTTPError as err:
        raise RuntimeError("Unable to upload to '{}'\n".format(destination))


# == Public API ===============================================================


def info(baseurl):
    return _fetch_json(baseurl + '/api/info')


def ls(baseurl, path):
    try:
        response = _fetch_json(baseurl + '/api/ls' + quote(path))
        if 'content' in response:
            return response['content']
        else:
            return [ response ]
    except HTTPError as err:
        raise RuntimeError("Unable to access to '{}'".format(path))


def mkdir(baseurl, path):
    try:
        postdata = codecs.encode(json.dumps({ 'dir': path }), 'utf-8')
        _urlopen(baseurl + '/api/fileops/mkdir', postdata).read()
    except HTTPError as err:
        raise RuntimeError("Unable to create '{}'".format(path))


def rm(baseurl, path):
    try:
        basedir, item = os.path.split(path)
        postdata = codecs.encode(json.dumps({ 'baseDir': basedir, 'items': [ item ] }), 'utf-8')
        _urlopen(baseurl + '/api/fileops/delete', postdata).read()
    except HTTPError as err:
        raise RuntimeError("Unable to delete '{}'".format(path))


def pull(baseurl, path, destination, log = None):
    _pull_recursive(baseurl, path, destination, log)
    

def push(baseurl, path, destination, log = None):
    _push_recursive(baseurl, path, destination, log)


# == CLI functions ============================================================


def _info(baseurl):
    inf = info(baseurl)
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


def _ls(baseurl, paths):
    for i, path in enumerate(paths):
        if len(paths) > 1:
            if i > 0:
                print('')
            print(path + ':')
        for item in ls(baseurl, path):
            print(_ls_item_to_str(item))


def _pull(baseurl, paths, destination):
    for path in paths:
        pull(baseurl, path, destination, print)


def _push(baseurl, paths, destination):
    for path in paths:
        push(baseurl, path, destination, print)


# == Main =====================================================================


if __name__ == '__main__':
    testurl = 'https://192.168.0.77:4443'
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
            mkdir(testurl, sys.argv[2])
        elif sys.argv[1] == 'rm':
            rm(testurl, sys.argv[2])
        sys.exit(0)
    except OSError as err:
        sys.stderr.write(str(err) + '\n')
        sys.exit(2)        
    except RuntimeError as err:
        sys.stderr.write(str(err.args[0]) + '\n')
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(3)
