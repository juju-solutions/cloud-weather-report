from unittest import TestCase

from mock import (
    Mock,
    patch,
)

from cloudweatherreport.cloudresource.aws import AWS


class TestAWS(TestCase):

    def test_is_instance_available(self):
        with patch('cloudweatherreport.cloudresource.aws.make_client',
                   autospec=True, return_value=make_fake_client()
                   ) as aws_mock:
            aws = AWS('access', 'secret', 'region')
            instance_available = aws.is_instance_available(1)
        self.assertIs(instance_available, True)
        aws_mock.assert_called_once_with('access', 'secret', 'region')

    def test_is_instance_available_max(self):
        with patch('cloudweatherreport.cloudresource.aws.make_client',
                   autospec=True, return_value=make_fake_client()
                   ) as aws_mock:
            aws = AWS('access', 'secret', 'region')
            instance_available = aws.is_instance_available(20)
        self.assertIs(instance_available, True)
        aws_mock.assert_called_once_with('access', 'secret', 'region')

    def test_is_instance_available_false(self):
        with patch('cloudweatherreport.cloudresource.aws.make_client',
                   autospec=True, return_value=make_fake_client()
                   ) as aws_mock:
            aws = AWS('access', 'secret', 'region')
            instance_available = aws.is_instance_available(21)
        self.assertIs(instance_available, False)
        aws_mock.assert_called_once_with('access', 'secret', 'region')

    def test_is_instance_available_some_terminated(self):
        with patch('cloudweatherreport.cloudresource.aws.make_client',
                   autospec=True, return_value=make_fake_client(
                    running_nodes=19, terminated_nodes=1)) as aws_mock:
            aws = AWS('access', 'secret', 'region')
            instance_available = aws.is_instance_available(1)
        self.assertIs(instance_available, True)
        aws_mock.assert_called_once_with('access', 'secret', 'region')

    def test_is_instance_available_max_instances(self):
        with patch('cloudweatherreport.cloudresource.aws.make_client',
                   autospec=True, return_value=make_fake_client(20)
                   ) as aws_mock:
            aws = AWS('access', 'secret', 'region')
            instance_available = aws.is_instance_available(1)
        self.assertIs(instance_available, False)
        aws_mock.assert_called_once_with('access', 'secret', 'region')

    def test_is_security_group_available(self):
        with patch('cloudweatherreport.cloudresource.aws.make_client',
                   autospec=True, return_value=make_fake_client()
                   ) as aws_mock:
            aws = AWS('access', 'secret', 'region')
            instance_available = aws.is_security_group_available(1)
        self.assertIs(instance_available, True)
        aws_mock.assert_called_once_with('access', 'secret', 'region')

    def test_is_security_group_available_max(self):
        with patch('cloudweatherreport.cloudresource.aws.make_client',
                   autospec=True, return_value=make_fake_client()
                   ) as aws_mock:
            aws = AWS('access', 'secret', 'region')
            instance_available = aws.is_security_group_available(500)
        self.assertIs(instance_available, True)
        aws_mock.assert_called_once_with('access', 'secret', 'region')

    def test_is_security_group_available_false(self):
        with patch('cloudweatherreport.cloudresource.aws.make_client',
                   autospec=True, return_value=make_fake_client()
                   ) as aws_mock:
            aws = AWS('access', 'secret', 'region')
            instance_available = aws.is_security_group_available(501)
        self.assertIs(instance_available, False)
        aws_mock.assert_called_once_with('access', 'secret', 'region')

    def test_is_security_group_available_max_groups(self):
        with patch('cloudweatherreport.cloudresource.aws.make_client',
                   autospec=True, return_value=make_fake_client(
                    number_of_security_group=500)) as aws_mock:
            aws = AWS('access', 'secret', 'region')
            instance_available = aws.is_security_group_available(1)
        self.assertIs(instance_available, False)
        aws_mock.assert_called_once_with('access', 'secret', 'region')


def make_fake_client(running_nodes=0, number_of_security_group=0,
                     terminated_nodes=0):
    client = Mock(
        spec=['list_nodes', 'ex_list_security_groups'],
        region_name='us-west-1')
    t_nodes = [Mock(state='terminated') for x in xrange(terminated_nodes)]
    nodes = [Mock(state='running') for x in xrange(running_nodes)]
    client.list_nodes.return_value = nodes + t_nodes
    security_groups = [x for x in xrange(number_of_security_group)]
    client.ex_list_security_groups.return_value = security_groups
    return client
