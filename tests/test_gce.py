from unittest import TestCase

from mock import (
    Mock,
    patch,
)

from cloudweatherreport.cloudresource.gce import (
    GCE,
    make_client,
)


class TestGCE(TestCase):
    regions = ['europe-west1', 'us-west1']
    zones = [['europe-west1-a', 'europe-west1-b'],
             ['us-west1-a', 'us-west1-b']]

    def test_get_region_from_zone(self):
        with patch('cloudweatherreport.cloudresource.gce.make_client',
                   autospec=True, return_value=make_fake_client()) as c_mock:
            gce = GCE('email', 'key', 'us-west1', 'p-id')
            region = gce.get_region_from_zone('us-west1-a')
            region2 = gce.get_region_from_zone('europe-west1-b')
        self.assertEqual(region, 'us-west1')
        self.assertEqual(region2, 'europe-west1')
        c_mock.assert_called_once_with('email', 'key', 'us-west1', 'p-id')

    def test_get_region_from_zone_error(self):
        with patch('cloudweatherreport.cloudresource.gce.make_client',
                   autospec=True, return_value=make_fake_client()):
            gce = GCE('email', 'key', 'us-west1', 'p-id')
            with self.assertRaisesRegexp(ValueError, 'Zone not found in re'):
                gce.get_region_from_zone('asia-west1-a')

    def test_get_cpu_size_from_node(self):
        node = make_fake_node()
        with patch('cloudweatherreport.cloudresource.gce.make_client',
                   autospec=True, return_value=make_fake_client()) as c_mock:
            gce = GCE('email', 'key', 'us-west1', 'p-id')
            cpu_size = gce.get_cpu_size_from_node(node)
        self.assertEqual(cpu_size, 1)
        c_mock.assert_called_once_with('email', 'key', 'us-west1', 'p-id')

    def test_get_cpu_size_from_node_error(self):
        node = make_fake_node(zone_name='foo')
        with patch('cloudweatherreport.cloudresource.gce.make_client',
                   autospec=True, return_value=make_fake_client()) as c_mock:
            gce = GCE('email', 'key', 'us-west1', 'p-id')
            with self.assertRaisesRegexp(ValueError, 'Machine type not found'):
                gce.get_cpu_size_from_node(node)
        c_mock.assert_called_once_with('email', 'key', 'us-west1', 'p-id')

    def test_filter_by_regions(self):
        nodes = [
            make_fake_node(zone_name='us-west1-a'),
            make_fake_node(zone_name='europe-west1-a')
        ]
        with patch('cloudweatherreport.cloudresource.gce.make_client',
                   autospec=True, return_value=make_fake_client()) as c_mock:
            gce = GCE('email', 'key', 'us-west1', 'p-id')
            filtered_nodes = gce.filter_by_region(nodes)
        self.assertEqual(filtered_nodes, [nodes[0]])
        c_mock.assert_called_once_with('email', 'key', 'us-west1', 'p-id')

    def test_is_instance_available(self):
        with patch('cloudweatherreport.cloudresource.gce.make_client',
                   autospec=True, return_value=make_fake_client()) as c_mock:
            gce = GCE('email', 'key', 'us-west1', 'p-id')
            result = gce.is_instance_available(1, 3)
            result2 = gce.is_instance_available(1, 23)
            result3 = gce.is_instance_available(199, 1)
        self.assertIs(result, True)
        self.assertIs(result2, True)
        self.assertIs(result3, True)
        c_mock.assert_called_once_with('email', 'key', 'us-west1', 'p-id')

    def test_is_instance_available_cpu_count_over_limit(self):
        with patch('cloudweatherreport.cloudresource.gce.make_client',
                   autospec=True, return_value=make_fake_client()) as c_mock:
            gce = GCE('email', 'key', 'us-west1', 'p-id')
            result = gce.is_instance_available(1, 24)
        self.assertIs(result, False)
        c_mock.assert_called_once_with('email', 'key', 'us-west1', 'p-id')

    def test_is_instance_available_instance_count_over_limit(self):
        with patch('cloudweatherreport.cloudresource.gce.make_client',
                   autospec=True, return_value=make_fake_client()) as c_mock:
            gce = GCE('email', 'key', 'us-west1', 'p-id')
            result = gce.is_instance_available(200, 1)
        self.assertIs(result, False)
        c_mock.assert_called_once_with('email', 'key', 'us-west1', 'p-id')

    def test_is_instance_available_all_over_limit(self):
        with patch('cloudweatherreport.cloudresource.gce.make_client',
                   autospec=True, return_value=make_fake_client()) as c_mock:
            gce = GCE('email', 'key', 'us-west1', 'p-id')
            result = gce.is_instance_available(200, 24)
        self.assertIs(result, False)
        c_mock.assert_called_once_with('email', 'key', 'us-west1', 'p-id')

    def test_is_secruity_group_available(self):
        with patch('cloudweatherreport.cloudresource.gce.make_client',
                   autospec=True, return_value=make_fake_client()) as c_mock:
            gce = GCE('email', 'key', 'us-west1', 'p-id')
            result = gce.is_security_group_available(1)
        self.assertIs(result, True)
        c_mock.assert_called_once_with('email', 'key', 'us-west1', 'p-id')

    def test_is_secruity_group_available_false(self):
        with patch('cloudweatherreport.cloudresource.gce.make_client',
                   autospec=True, return_value=make_fake_client()) as c_mock:
            gce = GCE('email', 'key', 'us-west1', 'p-id')
            result = gce.is_security_group_available(100)
        self.assertIs(result, False)
        c_mock.assert_called_once_with('email', 'key', 'us-west1', 'p-id')

    def test_is_secruity_group_available_false2(self):
        with patch('cloudweatherreport.cloudresource.gce.make_client',
                   autospec=True,
                   return_value=make_fake_client(number_of_security_group=100)
                   ) as c_mock:
            gce = GCE('email', 'key', 'us-west1', 'p-id')
            result = gce.is_security_group_available(1)
        self.assertIs(result, False)
        c_mock.assert_called_once_with('email', 'key', 'us-west1', 'p-id')

    def test_make_client(self):
        with patch('cloudweatherreport.cloudresource.gce.get_driver',
                   autospec=True) as gd_mock:
            client = make_client('email', 'key', 'us-west1', 'p-id')
        self.assertEqual(client, gd_mock.return_value())
        gd_mock.assert_called_once_with('gce')


def make_fake_node(zone_name='us-west1-a', state='running',
                   machine_type='http://...g1-small'):
    extra = {'zone': FakeZone(zone_name), 'machineType': machine_type}
    node = FakeNode(extra=extra, state=state)
    return node


def make_fake_sizes():
    return [make_fake_size('us-west1-a', 'http://...g1-small', 1),
            make_fake_size('us-west1-b', 'http://...h1-highcpu-4', 4)]


def make_fake_size(zone, self_link, guest_cpus):
    extra = {'selfLink': self_link, 'zone': FakeZone(name=zone),
             'guestCpus': guest_cpus}
    return FakeSize(extra=extra)


def make_fake_regions():
    all_regions = []
    for r, z in zip(TestGCE.regions, TestGCE.zones):
        zones = [FakeZone(name=zone) for zone in z]
        all_regions.append(FakeRegion(zones=zones, name=r))
    return all_regions


def make_fake_client(number_of_security_group=1):
    client = Mock(spec=['ex_get_region', 'ex_list_regions', 'list_sizes',
                        'list_nodes', 'ex_list_firewalls'])
    nodes = [make_fake_node(zone_name='us-west1-a'),
             make_fake_node(zone_name='europe-west1-a'),
             make_fake_node(zone_name='us-west1-a', state='terminated')]
    client.list_nodes.return_value = nodes
    client.ex_list_regions.return_value = make_fake_regions()
    client.list_sizes.return_value = make_fake_sizes()
    security_groups = [x for x in xrange(number_of_security_group)]
    client.ex_list_firewalls.return_value = security_groups
    return client


class FakeSize:
    def __init__(self, extra):
        self.extra = extra


class FakeNode:
    def __init__(self, extra, state='running'):
        self.state = state
        self.extra = extra


class FakeZone:
    def __init__(self, name):
        self.name = name


class FakeRegion:
    def __init__(self, zones, name):
        self.zones = zones
        self.name = name
