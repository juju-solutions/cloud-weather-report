import logging

from libcloud.compute.providers import get_driver
from libcloud.compute.types import Provider

from cloudweatherreport.cloudresource import CloudResource


__metaclass__ = type


class Azure(CloudResource):

    def __init__(self, tenant_id, subscription_id, application_id,
                 application_password, region, instance_limit=60,
                 security_group_limit=100, core_limit=20):
        super(Azure, self).__init__(
            instance_limit, security_group_limit, core_limit)
        self.client = make_client(
            tenant_id, subscription_id, application_id, application_password,
            region)
        self.region = region
        self.sizes = self.client.list_sizes()

    def is_instance_available(self, number_of_instances, number_of_cpus=None):
        nodes = self.client.list_nodes()
        # Remove other regions
        nodes = filter(lambda n: n.extra['location'] == self.region, nodes)
        # Remove terminated
        nodes = filter(lambda n: n.state != 'terminated', nodes)

        instance_count = len(nodes)
        logging.info('Azure instance request')
        instance_available = self.is_resource_available(
            number_of_instances, instance_count, self.instance_limit)

        cpu_count = sum([self.get_cpu_size_from_node(n) for n in nodes])
        logging.info('GCE CPU resource request')
        cpu_available = self.is_resource_available(
            number_of_cpus, cpu_count, self.cpu_limit)
        return cpu_available and instance_available

    def get_cpu_size_from_node(self, node):
        name = node.extra['properties']['hardwareProfile']['vmSize']
        for size in self.sizes:
            if name == size.name:
                return size.extra['numberOfCores']
        raise ValueError('Machine type not found.')

    def is_security_group_available(self, number_of_security_groups):
        # libcloud doesn't support listing Azure's network security groups
        raise NotImplemented


def make_client(tenant_id, subscription_id, application_id, secret, region):
    aws_driver = get_driver(Provider.AZURE_ARM)
    client = aws_driver(tenant_id, subscription_id, application_id, secret,
                        region=region)
    locations = [l.id for l in client.list_locations()]
    if region not in locations:
        raise ValueError(
            'Region not found. Available regions are {}'.format(locations))
    return client
