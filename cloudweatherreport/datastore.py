import os
from time import sleep
from contextlib import contextmanager
from ConfigParser import ConfigParser
from mimetypes import MimeTypes
from uuid import uuid4
from boto.s3.connection import S3Connection


class TimeoutError(Exception):
    pass


class DataStore(object):
    """
    Base class for data store implementations.
    """

    @classmethod
    def get(cls, prefix, s3_bucket=None, s3_creds_file=None):
        """
        Get a LocalDataStore or S3DataStore instance depending on whether
        S3 is provided.
        """
        if s3_bucket:
            return S3DataStore(prefix,
                               s3_bucket,
                               s3_creds_file)
        else:
            return LocalDataStore(prefix)

    def __init__(self, prefix):
        self.prefix = prefix

    def _path(self, *components):
        components = [c.strip('/') for c in components if c and c.strip('/')]
        return '/'.join([self.prefix] + components)

    def list(self, path=None):
        """
        List contents of a path in the data store, in modification order
        (most recently modified last).
        """
        raise NotImplementedError()

    def exists(self, filename):
        """
        Test if a file exists in the data store.
        """
        raise NotImplementedError()

    def read(self, filename):
        """
        Read a file from the data store.
        """
        raise NotImplementedError()

    def write(self, filename, contents, encoding='utf8'):
        """
        Write a file to the data store.
        """
        raise NotImplementedError()

    def delete(self, filename):
        """
        Delete a file from the data store.
        """
        raise NotImplementedError()

    @contextmanager
    def lock(self, timeout=5*60):
        """
        Context manager that acquires a lock for the datastore.

        Blocks until the lock is acquired or the timeout (in seconds) is
        reached (at which a `TimeoutError` is raised).

        This depends on the underlying store supporting read-after-write
        consistency for new files, and eventual consistency for deleted
        files.
        """
        # S3 ensures read-after-write consistency for new objects, and eventual
        # consistency for updates or deletes.  This implements an optimistic
        # locking strategy by leveraging the RAW of new objects.

        # Optimistically create our unique lock file.  This relies on RAW
        # consistency to ensure it will be immediately visible to others,
        # and their lock files to us.
        lock_id = uuid4()
        lock_filename = '.lock.{}'.format(lock_id)
        self.write(lock_filename, '')
        try:
            # wait until we own the earliest lock file, and thus the lock
            wait_secs = 1
            total_waited = 0
            while self._active_lock_filename() != lock_filename:
                sleep(wait_secs)
                total_waited += wait_secs
                if total_waited >= timeout:
                    raise TimeoutError('Timed out waiting for lock')
                # increase sleep time a second at a time, up to 10s
                if wait_secs < 10:
                    wait_secs += 1
            yield lock_id
        finally:
            self.delete(lock_filename)

    def _active_lock_filename(self):
        for filename in self.list():
            if filename.startswith('.lock.'):
                return filename


class LocalDataStore(DataStore):
    """
    Data store implementation using the local (posix) filesystem.
    """

    def list(self, path=None):
        """
        List contents of a path in the data store, in modification order
        (most recently modified last).
        """
        basepath = self._path(path)
        if not os.path.exists(basepath):
            return []

        def mtime(fn):
            return os.stat(self._path(path, fn)).st_mtime
        return sorted(os.listdir(basepath), key=mtime)

    def exists(self, filename):
        """
        Test if a file exists in the data store.
        """
        return os.path.exists(self._path(filename))

    def read(self, filename, encoding='utf8'):
        """
        Read a file from the data store.
        """
        with open(self._path(filename)) as fp:
            return fp.read().decode(encoding)

    def write(self, filename, contents, encoding='utf8'):
        """
        Write a file to the data store.
        """
        filename = self._path(filename)
        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        with open(filename, 'w') as fp:
            fp.write(contents.encode(encoding))

    def delete(self, filename):
        """
        Delete a file from the data store.
        """
        filename = self._path(filename)
        os.remove(filename)


class S3DataStore(DataStore):
    """
    Data store implementation using Amazon's S3.
    """

    def __init__(self, prefix, bucket_name, creds_file):
        super(S3DataStore, self).__init__(prefix)
        config = ConfigParser()
        with open(creds_file) as fp:
            config.readfp(fp)
        self.access_key = config.get('default', 'access_key')
        self.secret_key = config.get('default', 'secret_key')
        self.bucket_name = bucket_name
        self._bucket = None

    @property
    def bucket(self):
        if self._bucket is None:
            conn = S3Connection(self.access_key, self.secret_key)
            if conn.lookup(self.bucket_name):
                self._bucket = conn.get_bucket(self.bucket_name)
            else:
                self._bucket = conn.create_bucket(self.bucket_name)
        return self._bucket

    def list(self, path=None):
        """
        List contents of a path in the data store, in modification order
        (most recently modified last).
        """
        basepath = self._path(path)
        basepath = basepath.rstrip('/') + '/'

        def mtime(keyobj):
            return keyobj.last_modified
        paths = self.bucket.list(basepath, '/')
        files = [k for k in paths if hasattr(k, 'last_modified')]
        return [key.name.split('/')[-1] for key in sorted(files, key=mtime)]

    def exists(self, filename):
        """
        Test if a file exists in the data store.
        """
        filename = self._path(filename)
        return self.bucket.get_key(filename) is not None

    def read(self, filename, encoding='utf-8'):
        """
        Read a file from the data store.
        """
        key = self.bucket.get_key(self._path(filename))
        return key.get_contents_as_string(encoding=encoding)

    def write(self, filename, contents, encoding='utf8'):
        """
        Write a file to the data store.
        """
        mime = MimeTypes()
        mime.add_type('text/x-yaml', '.yaml')
        content_type, _ = mime.guess_type(filename)
        key = self.bucket.new_key(self._path(filename))
        key.set_contents_from_string(contents.encode(encoding), {
            'Content-Type': content_type or 'text/plain',
            'Content-Encoding': encoding,
        })

    def delete(self, filename):
        """
        Delete a file from the data store.
        """
        if self.exists(filename):
            self.bucket.delete_key(self._path(filename))
