import logging

from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver
from libcloud.common.google import ResourceNotFoundError

from cloudweatherreport.cloudresource import CloudResource


class GCE(CloudResource):
    """Determines if the requested resources are available for GCE cloud."""

    def __init__(self, sa_email, key, region, project_id,
                 instance_limit=200, security_group_limit=100, cpu_limit=24):
        super(GCE, self).__init__(
            instance_limit, security_group_limit, cpu_limit)
        self.region = region
        self.client = make_client(sa_email, key, region, project_id)
        self.regions = self.client.ex_list_regions()
        self.sizes = self.client.list_sizes()

    def is_instance_available(self, number_of_instances, number_of_cpus=None):
        """Return True if the num of requested CPUs and instances are available

        :param number_of_instances: Number of requested instances.
        :param number_of_cpu: Number of CPUs requested.
        :return: boolean
        """
        nodes = self.client.list_nodes()
        nodes = self.filter_by_region(nodes)
        # Remove terminated
        nodes = [n for n in nodes if n.state != 'terminated']
        instance_count = len(nodes)
        logging.info('GCE instance request')
        instance_available = self.is_resource_available(
            number_of_instances, instance_count, self.instance_limit)
        cpu_count = sum([self.get_cpu_size_from_node(n) for n in nodes])
        logging.info('GCE CPU resource request')
        cpu_available = self.is_resource_available(
            number_of_cpus, cpu_count, self.cpu_limit)
        return cpu_available and instance_available

    def get_cpu_size_from_node(self, node):
        """Return CPU count for the node."""
        machine_type = node.extra['machineType']
        zone = node.extra['zone'].name
        for size in self.sizes:
            if (size.extra['selfLink'] == machine_type and
                    size.extra['zone'].name == zone):
                return size.extra['guestCpus']
        raise ValueError('Machine type not found.')

    def filter_by_region(self, nodes):
        filtered_nodes = []
        for node in nodes:
            zone = node.extra['zone'].name
            region = self.get_region_from_zone(zone)
            if region == self.region:
                filtered_nodes.append(node)
        return filtered_nodes

    def get_region_from_zone(self, zone):
        """Return region name from zone.

        :param  zone: Zone name
        :return:  Region name
        """
        for region in self.regions:
            zones = [z.name for z in region.zones]
            if zone in zones:
                return region.name
        raise ValueError("Zone not found in region.")

    def is_security_group_available(self, request):
        """Return True if the num of requested security groups are available.

        :param request: Number of requested security groups.
        :return: boolean
        """
        security_group_count = len(self.client.ex_list_firewalls())
        logging.info("GCE security groups resource request")
        return self.is_resource_available(
            request, security_group_count, self.security_group_limit)


def make_client(sa_email, key, region, project_id):
    """Return libcloud client.

    :param sa_email: Service account email.
    :param key: The RSA Key (for service accounts) or file path containing key.
    :param project_id: Google project id.
    :param region: Region name (not a Zone name)
    """
    gce_driver = get_driver(Provider.GCE)
    client = gce_driver(sa_email, key, project=project_id)
    # Explicitly check if the region exists.
    try:
        client.ex_get_region(region)
    except ResourceNotFoundError:
        raise ValueError("Unknown region: {}".format(region))
    return client
