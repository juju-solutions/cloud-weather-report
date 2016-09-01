import os
import shutil
from unittest import TestCase
from tempfile import mkdtemp
from time import sleep

import mock

from cloudweatherreport import datastore


class TestDataStore(TestCase):
    @mock.patch.object(datastore.S3DataStore, '__init__')
    def test_get(self, ds___init__):
        ds___init__.return_value = None
        self.assertIsInstance(datastore.DataStore.get('prefix'),
                              datastore.LocalDataStore)
        self.assertIsInstance(datastore.DataStore.get('prefix', 'foo', 'cred'),
                              datastore.S3DataStore)

    @mock.patch.object(datastore, 'uuid4')
    @mock.patch.object(datastore, 'sleep')
    @mock.patch.object(datastore.DataStore, 'delete')
    @mock.patch.object(datastore.DataStore, '_active_lock_filename')
    @mock.patch.object(datastore.DataStore, 'write')
    def test_lock(self, ds_write, ds_alf, ds_delete, ds_sleep, ds_uuid4):
        ds = datastore.DataStore('prefix')
        ds_uuid4.return_value = 'uuid'

        # test no contest
        ds_alf.return_value = '.lock.uuid'
        with ds.lock():
            ds_write.assert_called_once_with('.lock.uuid', '')
            ds_alf.assert_called_once_with()
            assert not ds_sleep.called
            assert not ds_delete.called
        ds_delete.assert_called_once_with('.lock.uuid')

        # test timeout
        ds_delete.reset_mock()
        ds_alf.return_value = '.lock.other'
        with self.assertRaises(datastore.TimeoutError):
            with ds.lock(60):
                pass
        assert ds_delete.called
        self.assertEqual(ds_sleep.call_args_list, [
            mock.call(1),
            mock.call(2),
            mock.call(3),
            mock.call(4),
            mock.call(5),
            mock.call(6),
            mock.call(7),
            mock.call(8),
            mock.call(9),
            mock.call(10),
            mock.call(10),
        ])

        # test contest
        ds_alf.side_effect = ['.lock.else', '.lock.else', '.lock.uuid']
        ds_sleep.reset_mock()
        ds_delete.reset_mock()
        with ds.lock('path'):
            pass
        self.assertEqual(ds_sleep.call_args_list, [
            mock.call(1),
            mock.call(2),
        ])
        ds_delete.assert_called_once_with('.lock.uuid')

    @mock.patch.object(datastore.DataStore, 'list')
    def test_active_lock_filename(self, ds_list):
        ds_list.return_value = [
            'bar',
            '.lock.one',
            '.lock.two',
            'qux',
        ]
        ds = datastore.DataStore('prefix')
        self.assertEquals(ds._active_lock_filename(), '.lock.one')
        ds_list.return_value = [
            'bar',
            'qux',
        ]
        self.assertIsNone(ds._active_lock_filename())


class TestLocalDataStore(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prefix = mkdtemp()
        os.mkdir('/'.join([cls.prefix, 'path']))
        filenames = [
            'file2',
            'file1',
            'path/file3',
            'path/file4',
        ]
        for filename in filenames:
            with open('/'.join([cls.prefix, filename]), 'w') as fp:
                fp.write(filename)
            # sleep a tiny amount to ensure that the mtime on the files
            # differs enough to make the time the primary sort criteria
            sleep(0.05)
        cls.ds = datastore.LocalDataStore(cls.prefix)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.prefix)

    def test_list(self):
        self.assertEqual(self.ds.list(), [
            'file2',
            'file1',
            'path',
        ])
        self.assertEqual(self.ds.list('path'), [
            'file3',
            'file4',
        ])
        self.assertEqual(self.ds.list('other'), [])
        with mock.patch.object(os, 'stat') as mstat:
            # test all files having same mtime and ensure
            # they fall back to sorting by name
            mstat.return_value = mock.Mock(st_mtime=1)
            self.assertEqual(self.ds.list(), [
                'file1',
                'file2',
                'path',
            ])

    def test_exists(self):
        self.assertTrue(self.ds.exists('file1'))
        self.assertTrue(self.ds.exists('path/file3'))
        self.assertFalse(self.ds.exists('file5'))
        self.assertFalse(self.ds.exists('path/file6'))

    def test_read(self):
        self.assertEqual(self.ds.read('file1'), 'file1')
        self.assertEqual(self.ds.read('path/file3'), 'path/file3')

    def test_write(self):
        self.ds.write('new', 'new')
        self.assertEqual(self.ds.read('new'), 'new')
        self.ds.write('path/new', 'new')
        self.assertEqual(self.ds.read('path/new'), 'new')
        self.ds.write('new_path/new', 'new')
        self.assertEqual(self.ds.read('new_path/new'), 'new')

    def test_delete(self):
        self.ds.write('test_del', '')
        assert self.ds.exists('test_del')
        self.ds.delete('test_del')
        assert not self.ds.exists('test_del')

    def test_lock(self):
        # test lock
        with self.ds.lock(timeout=1) as lock_id:
            assert self.ds.exists('.lock.{}'.format(lock_id))
        assert not self.ds.exists('.lock.{}'.format(lock_id))
        # test lock gets cleaned up on error
        try:
            with self.ds.lock(timeout=1) as lock_id:
                assert self.ds.exists('.lock.{}'.format(lock_id))
                raise ValueError('test')
        except ValueError:
            pass
        assert not self.ds.exists('.lock.{}'.format(lock_id))
        # test lock timeout
        with mock.patch.object(datastore, 'uuid4') as muuid4:
            # ensure that the lock files are ordered as we expect,
            # even if they end up with the same mtime
            muuid4.side_effect = ['1', '2']
            with self.ds.lock(timeout=1):
                with self.assertRaises(datastore.TimeoutError):
                    with self.ds.lock(timeout=1):
                        self.fail('Secondary lock should fail')


class TestS3DataStore(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = mkdtemp()
        cls.credsfile = cls.tempdir + '/test.creds'
        with open(cls.credsfile, 'w') as fp:
            fp.writelines([
                '[default]\n',
                'access_key=access\n',
                'secret_key=secret\n',
            ])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tempdir)

    def setUp(self):
        self.ds = datastore.S3DataStore('prefix', 'bucket', self.credsfile)
        self.s3conn_p = mock.patch.object(datastore, 'S3Connection')
        self.S3Connection = self.s3conn_p.start()
        self.addCleanup(self.s3conn_p.stop)

    def test_init(self):
        self.assertEqual(self.ds.prefix, 'prefix')
        self.assertEqual(self.ds.bucket_name, 'bucket')
        self.assertEqual(self.ds.access_key, 'access')
        self.assertEqual(self.ds.secret_key, 'secret')

    def test_bucket(self):
        self.S3Connection.return_value.get_bucket.return_value = 'old'
        self.S3Connection.return_value.create_bucket.return_value = 'new'
        assert not self.S3Connection.called
        self.assertEqual(self.ds.bucket, 'old')
        self.S3Connection.assert_called_once_with('access', 'secret')

        self.S3Connection.reset_mock()
        self.assertEqual(self.ds.bucket, 'old')
        assert not self.S3Connection.called

        self.S3Connection.return_value.lookup.return_value = None
        self.ds._bucket = None
        self.assertEqual(self.ds.bucket, 'new')

    def test_list(self):
        def key(name, modified):
            key = mock.Mock()
            key.name = name  # Mock(name=foo) doesn't work :(
            key.last_modified = modified
            return key

        self.ds.bucket.list.side_effect = [
            [
                key('file1', '2016-08-01T00:00:00.000Z'),
                key('file2', '2016-08-02T00:00:00.000Z'),
            ],
            [
                key('file2', '2016-08-02T00:00:00.000Z'),
                key('file1', '2016-08-01T00:00:00.000Z'),
            ],
        ]
        self.assertEqual(self.ds.list(), ['file1', 'file2'])
        self.assertEqual(self.ds.list('path'), ['file1', 'file2'])
        self.assertEqual(self.ds.bucket.list.call_args_list, [
            mock.call('prefix/', '/'),
            mock.call('prefix/path/', '/'),
        ])

    def test_exists(self):
        self.ds.bucket.get_key.side_effect = [None, mock.Mock()]
        self.assertFalse(self.ds.exists('file1'))
        self.assertTrue(self.ds.exists('path/file2'))
        self.assertEqual(self.ds.bucket.get_key.call_args_list, [
            mock.call('prefix/file1'),
            mock.call('prefix/path/file2'),
        ])

    def test_read(self):
        gcas = self.ds.bucket.get_key.return_value.get_contents_as_string
        gcas.return_value = 'content'
        self.assertEqual(self.ds.read('file1', 'ascii'), 'content')
        self.ds.bucket.get_key.assert_called_once_with('prefix/file1')
        gcas.assert_called_once_with(encoding='ascii')

    def test_write(self):
        self.ds.write('file1.yaml', 'contents', 'ascii')
        self.ds.bucket.new_key.assert_called_once_with('prefix/file1.yaml')
        key = self.ds.bucket.new_key.return_value
        key.set_contents_from_string.assert_called_once_with(
            'contents', {
                'Content-Type': 'text/x-yaml',
                'Content-Encoding': 'ascii',
            })

    def test_delete(self):
        self.ds.delete('test_del')
        self.ds.bucket.delete_key.assert_called_once_with('prefix/test_del')
