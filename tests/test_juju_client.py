from unittest import TestCase

from mock import (
    patch,
)

from cloudweatherreport.juju_client import JujuClient

__metaclass__ = type


class TestJujuClient(TestCase):

    def test_full_args(self):
        jc = self.make_client()
        full = jc._full_args('bar', ('baz', 'qux'))
        self.assertEqual(('juju', '--show-log', 'bar', '-e', 'foo', 'baz',
                          'qux'), full)
        full = jc._full_args('bar', ('baz', 'qux'))
        self.assertEqual((
            'juju', '--show-log', 'bar', '-e', 'foo',
            'baz', 'qux'), full)
        jc.env_name = None
        full = jc._full_args('bar', ('baz', 'qux'))
        self.assertEqual(('juju', '--show-log', 'bar', 'baz', 'qux'), full)

    def test_full_args_action(self):
        jc = self.make_client()
        full = jc._full_args('action bar', ('baz', 'qux'))
        self.assertEqual((
            'juju', '--show-log', 'action', 'bar', '-e', 'foo', 'baz', 'qux'),
            full)

    def test_get_juju_output(self):

        def asdf(x, stderr):
            return 'asdf'

        client = self.make_client()
        with patch('subprocess.check_output', side_effect=asdf) as mock:
            result = client.get_juju_output('bar')
        self.assertEqual('asdf', result)
        self.assertEqual((('juju', '--show-log', 'bar', '-e', 'foo'),),
                         mock.call_args[0])

    def test_get_juju_output_accepts_varargs(self):

        def asdf(x, stderr):
            return 'asdf'

        b = self.make_client()
        with patch('subprocess.check_output', side_effect=asdf) as mock:
            result = b.get_juju_output('bar', 'baz', '--qux')
        self.assertEqual('asdf', result)
        self.assertEqual((('juju', '--show-log', 'bar', '-e', 'foo', 'baz',
                           '--qux'),), mock.call_args[0])

    def test_action_do(self):
        b = self.make_client()
        with patch.object(b, 'get_juju_output') as mock:
            mock.return_value = \
                "Action queued with id: 5a92ec93-d4be-4399-82dc-7431dbfd08f9"
            id = b.action_do("foo/0", "myaction", "param=5")
            self.assertEqual(id, "5a92ec93-d4be-4399-82dc-7431dbfd08f9")
        mock.assert_called_once_with(
            'action do', 'foo/0', 'myaction', "param=5"
        )

    def test_action_do_error(self):
        b = self.make_client()
        with patch.object(b, 'get_juju_output') as mock:
            mock.return_value = "some bad text"
            with self.assertRaisesRegexp(Exception,
                                         "Action id not found in output"):
                b.action_do("foo/0", "myaction", "param=5")

    def test_action_fetch(self):
        b = self.make_client()
        with patch.object(b, 'get_juju_output') as mock:
            ret = "status: completed\nfoo: bar"
            mock.return_value = ret
            out = b.action_fetch("123")
            self.assertEqual(out, ret)
        mock.assert_called_once_with(
            'action fetch', '123', "--wait", "1m"
        )

    def test_action_do_fetch(self):
        b = self.make_client()
        with patch.object(b, 'get_juju_output') as mock:
            ret = "status: completed\nfoo: bar"
            mock.side_effect = [
                "Action queued with id: 5a92ec93-d4be-4399-82dc-7431dbfd08f9",
                ret]
            out = b.action_do_fetch("foo/0", "myaction", "param=5")
            self.assertEqual(out, ret)

    def make_client(self):
        return JujuClient(env_name='foo')
