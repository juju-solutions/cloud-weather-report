from unittest import TestCase

from mock import (
    Mock,
    patch,
)

from cloudweatherreport.cloudresource.azure import (
    Azure,
    make_client,
)


class TestAzure(TestCase):

    def test_get_cpu_size_from_node(self):
        node = make_fake_node()
        client = make_fake_client()
        with patch('cloudweatherreport.cloudresource.azure.make_client',
                   autospec=True, return_value=client) as c_mock:
            azure = Azure('t-id', 's-id', 'a-id', 'key', 'region')
            cpu_count = azure.get_cpu_size_from_node(node)
            self.assertEqual(cpu_count, 4)
        c_mock.assert_called_once_with('t-id', 's-id', 'a-id', 'key', 'region')

    def test_is_instance_available(self):
        client = make_fake_client()
        with patch('cloudweatherreport.cloudresource.azure.make_client',
                   autospec=True, return_value=client) as c_mock:
            azure = Azure('t-id', 's-id', 'a-id', 'key', 'westus')
            result = azure.is_instance_available(1, 1)
            self.assertIs(result, True)
        c_mock.assert_called_once_with('t-id', 's-id', 'a-id', 'key', 'westus')

    def test_is_instance_available_max_core(self):
        client = make_fake_client()
        with patch('cloudweatherreport.cloudresource.azure.make_client',
                   autospec=True, return_value=client) as c_mock:
            azure = Azure(
                't-id', 's-id', 'a-id', 'key', 'westus', core_limit=20)
            # Nine core already running
            result = azure.is_instance_available(1, 11)
            self.assertIs(result, True)
        c_mock.assert_called_once_with('t-id', 's-id', 'a-id', 'key', 'westus')

    def test_is_instance_available_max_instance(self):
        client = make_fake_client()
        with patch('cloudweatherreport.cloudresource.azure.make_client',
                   autospec=True, return_value=client) as c_mock:
            azure = Azure(
                't-id', 's-id', 'a-id', 'key', 'westus', instance_limit=60)
            # Three instance already running
            result = azure.is_instance_available(57, 1)
            self.assertIs(result, True)
        c_mock.assert_called_once_with('t-id', 's-id', 'a-id', 'key', 'westus')

    def test_is_instance_available_no_core(self):
        client = make_fake_client()
        with patch('cloudweatherreport.cloudresource.azure.make_client',
                   autospec=True, return_value=client) as c_mock:
            azure = Azure(
                't-id', 's-id', 'a-id', 'key', 'westus', core_limit=9)
            result = azure.is_instance_available(1, 1)
            self.assertIs(result, False)
        c_mock.assert_called_once_with('t-id', 's-id', 'a-id', 'key', 'westus')

    def test_is_instance_available_no_instance(self):
        client = make_fake_client()
        with patch('cloudweatherreport.cloudresource.azure.make_client',
                   autospec=True, return_value=client) as c_mock:
            azure = Azure(
                't-id', 's-id', 'a-id', 'key', 'westus', instance_limit=3)
            result = azure.is_instance_available(1, 1)
            self.assertIs(result, False)
        c_mock.assert_called_once_with('t-id', 's-id', 'a-id', 'key', 'westus')

    def test_is_instance_available_no_core_no_instance(self):
        client = make_fake_client()
        with patch('cloudweatherreport.cloudresource.azure.make_client',
                   autospec=True, return_value=client) as c_mock:
            azure = Azure(
                't-id', 's-id', 'a-id', 'key', 'westus', instance_limit=3,
                core_limit=9)
            result = azure.is_instance_available(1, 1)
            self.assertIs(result, False)
        c_mock.assert_called_once_with('t-id', 's-id', 'a-id', 'key', 'westus')

    def test_make_client(self):
        with patch('cloudweatherreport.cloudresource.azure.get_driver',
                   autospec=True) as gd_mock:
            gd_mock.return_value().list_locations.return_value = [
                Mock(id='westus')]
            client = make_client('t-id', 's-id', 'a-id', 'key', 'westus')
        self.assertEqual(client, gd_mock.return_value())
        gd_mock.assert_called_once_with('azure_arm')

    def test_make_client_error(self):
        with patch('cloudweatherreport.cloudresource.azure.get_driver',
                   autospec=True) as gd_mock:
            gd_mock.return_value().list_locations.return_value = [
                Mock(id='westus')]
            with self.assertRaisesRegexp(
                    ValueError,
                    "Region not found. Available regions are \['westus'\]"):
                make_client('t-id', 's-id', 'a-id', 'key', 'foo')
        gd_mock.assert_called_once_with('azure_arm')


def make_fake_sizes():
    extra = {'numberOfCores': 1}
    size = Mock(extra=extra)
    size.configure_mock(name='Standard_D1')
    extra = {'numberOfCores': 4}
    size2 = Mock(extra=extra)
    size2.configure_mock(name='Standard_A3')
    return [size, size2]


def make_fake_node(location='westus', state='running', vm_size='Standard_A3'):
    extra = {'properties': {'hardwareProfile': {'vmSize': vm_size}},
             'location': location}
    node = Mock(spec=[], extra=extra, state=state)
    return node


def make_fake_client():
    # Creates 3 nodes running with 9 cores and 1 terminated node in westus
    # One node in centernalus
    nodes = [
        make_fake_node(),
        make_fake_node(),
        make_fake_node(vm_size='Standard_D1'),
        make_fake_node(vm_size='Standard_D1', state='terminated'),
        make_fake_node('centernalus')]
    sizes = make_fake_sizes()
    client = Mock(spec=['list_sizes', 'list_nodes'])
    client.list_sizes.return_value = sizes
    client.list_nodes.return_value = nodes
    return client
