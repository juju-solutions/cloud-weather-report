import logging

from libcloud.compute.providers import get_driver
from libcloud.compute.types import Provider

from cloudweatherreport.cloudresource import CloudResource


__metaclass__ = type


INSTANCE_LIMIT = 20
SECURITY_GROUP_LIMIT = 500


class AWS(CloudResource):
    """Determines if the requested resources are available for AWS cloud."""

    def __init__(self, access_key, secret_key, region,
                 instance_limit=INSTANCE_LIMIT,
                 security_group_limit=SECURITY_GROUP_LIMIT):
        super(AWS, self).__init__(instance_limit, security_group_limit, None)
        self.client = make_client(access_key, secret_key, region)
        self.region = region

    def is_instance_available(self, number_of_instances, _=None):
        """Return True if the number of requested instances are available.

        :param number_of_instances: Number of requested instance.
        :param _: Number of CPUs are ignored for AWS.
        :return: boolean
        """
        nodes = self.client.list_nodes()
        terminated = len([n for n in nodes if n.state == 'terminated'])
        instance_count = len(nodes) - terminated
        logging.debug("AWS total instance:{} terminated:{} region:{}".format(
            len(nodes), terminated, self.region))
        return self.is_resource_available(
            number_of_instances, instance_count, self.instance_limit)

    def is_security_group_available(self, request):
        """Return True if the num of requested security groups are available.

        :param request: Number of requested security groups.
        :return: boolean
        """
        security_group_count = len(self.client.ex_list_security_groups())
        logging.debug("AWS security groups. Region:{}".format(self.region))
        return self.is_resource_available(
            request, security_group_count, self.security_group_limit)


def make_client(access_key, secret_key, region):
    aws_driver = get_driver(Provider.EC2)
    return aws_driver(access_key, secret_key, region=region)
