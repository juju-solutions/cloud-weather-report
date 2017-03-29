from contextlib import contextmanager
from ConfigParser import ConfigParser
import datetime
import logging
import os
from mimetypes import MimeTypes
from time import sleep, time
from uuid import uuid4

from boto.s3.connection import S3Connection


log = logging.getLogger(__name__)


class TimeoutError(Exception):
    pass


class DataStore(object):
    """
    Base class for data store implementations.
    """

    @classmethod
    def get(cls, prefix, s3_bucket=None, s3_creds_file=None, public=True):
        """
        Get a LocalDataStore or S3DataStore instance depending on whether
        S3 is provided.
        """
        if s3_bucket:
            return S3DataStore(prefix,
                               s3_bucket,
                               s3_creds_file,
                               public)
        else:
            return LocalDataStore(prefix)

    def __init__(self, prefix):
        self.prefix = prefix

    def _path(self, *components):
        components = [c.strip('/') for c in components if c and c.strip('/')]
        return '/'.join([self.prefix] + components)

    def list(self, path=None):
        """
        List contents of a path in the data store, sorted by modification
        (oldest first, most recently modified last) then name.
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
    def lock(self, timeout=5*60, old_lock_age=60*60):
        """
        Context manager that acquires a lock for the datastore.

        Blocks until the lock is acquired or the timeout (in seconds) is
        reached (at which a `TimeoutError` is raised).

        This depends on the underlying store supporting read-after-write
        consistency for new files, and eventual consistency for deleted
        files.

        :param timeout:  Timeout in seconds to acquire a lock.
        :param old_lock_age: Old lock age in seconds. If set to a number,
          it deletes all other locks older than old_lock_age.
        """
        # S3 ensures read-after-write consistency for new objects, and eventual
        # consistency for updates or deletes.  This implements an optimistic
        # locking strategy by leveraging the RAW of new objects.

        # Optimistically create our unique lock file.  This relies on RAW
        # consistency to ensure it will be immediately visible to others,
        # and their lock files to us.
        lock_id = self.create_lock_id()
        lock_filename = '.lock.{}'.format(lock_id)
        self.write(lock_filename, '')
        log.debug("Trying to acquire datastore lock {}".format(lock_filename))
        try:
            # wait until we own the earliest lock file, and thus the lock
            wait_secs = 1
            total_waited = 0
            active_lock = self._active_lock_filename()
            while active_lock != lock_filename:
                log.debug('Lock already acquired {} age:{} sec.'.format(
                    active_lock, int(self.age_in_seconds(active_lock))))
                self.delete_lock_if_old(active_lock, old_lock_age)
                sleep(wait_secs)
                total_waited += wait_secs
                if total_waited >= timeout:
                    raise TimeoutError(
                        'Timed out waiting for lock:{}'.format(lock_filename))
                # increase sleep time a second at a time, up to 10s
                if wait_secs < 10:
                    wait_secs += 1
                active_lock = self._active_lock_filename()
            log.debug('Datastore lock acquired {}'.format(lock_filename))
            yield lock_id
        finally:
            log.debug('Datastore lock released {}'.format(lock_filename))
            self.delete(lock_filename)

    def create_lock_id(self):
        """Create lock id.

        If it is running in Jenkins, it will postfix the lock id with the job
        name and build number.
        """
        job_name = os.getenv('JOB_NAME')
        build_number = os.getenv('BUILD_NUMBER')
        if job_name and build_number:
            return '{}.{}.{}'.format(uuid4(), job_name, build_number)
        return uuid4()

    def delete_lock_if_old(self, lock, old_age):
        """Delete a lock older than old_age."""
        age = self.age_in_seconds(lock)
        if old_age is not None and age > old_age:
            log.info('Deleting old datastore lock:{} age:{} sec'.format(
                lock, int(age)))
            self.delete(lock)

    def age_in_seconds(self, filename):
        """
        File age in seconds.
        """
        raise NotImplementedError()

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
        List contents of a path in the data store, sorted by modification
        (oldest first, most recently modified last) then name.
        """
        basepath = self._path(path)
        if not os.path.exists(basepath):
            return []

        def mtime(fn):
            return (os.stat(self._path(path, fn)).st_mtime, fn)
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

    def age_in_seconds(self, filename):
        return time() - os.path.getmtime(self._path(filename))


class S3DataStore(DataStore):
    """
    Data store implementation using Amazon's S3.
    """

    def __init__(self, prefix, bucket_name, creds_file, public,
                 debug_level=logging.INFO):
        super(S3DataStore, self).__init__(prefix)
        config = ConfigParser()
        with open(creds_file) as fp:
            config.readfp(fp)
        self.access_key = config.get('default', 'access_key')
        self.secret_key = config.get('default', 'secret_key')
        self.bucket_name = bucket_name
        self._bucket = None
        self.public = public
        self.set_logging(debug_level)

    @property
    def bucket(self):
        if self._bucket is None:
            conn = S3Connection(self.access_key, self.secret_key)
            if conn.lookup(self.bucket_name):
                self._bucket = conn.get_bucket(self.bucket_name)
            else:
                self._bucket = conn.create_bucket(self.bucket_name)
        return self._bucket

    @staticmethod
    def set_logging(level):
        logger = logging.getLogger('boto')
        logger.propagate = False
        logger.setLevel(level)

    def list(self, path=None):
        """
        List contents of a path in the data store, sorted by modification
        (oldest first, most recently modified last) then name.
        """
        basepath = self._path(path)
        basepath = basepath.rstrip('/') + '/'

        def mtime(keyobj):
            return (keyobj.last_modified, keyobj.name)
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
        if self.public:
            key.set_canned_acl('public-read')

    def delete(self, filename):
        """
        Delete a file from the data store.
        """
        if self.exists(filename):
            self.bucket.delete_key(self._path(filename))

    def age_in_seconds(self, filename):
        key = self.bucket.get_key(self._path(filename))
        # Date format return from boto: Tue, 28 Mar 2017 13:30:37 GMT
        # The last_modified attirbute has different date format for the
        # bucket.list() and bucket.get_key() functions.
        modified = datetime.datetime.strptime(
            key.last_modified, '%a, %d %b %Y %H:%M:%S %Z')
        return (datetime.datetime.utcnow() - modified).total_seconds()
