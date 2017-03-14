import logging

import libcloud

from cloudweatherreport.cloudresource import CloudResource

__metaclass__ = type


class AWS(CloudResource):

    def __init__(self, access_key, secret_key, region, instance_limit=20,
                 security_group_limit=500):
        super(AWS, self).__init__(instance_limit, security_group_limit)
        self.client = make_client(access_key, secret_key, region)

    def is_instance_available(self, instance_needed):
        nodes = self.client.list_nodes()
        terminated = [n for n in nodes if n.state == 'terminated']
        instance_count = len(nodes) - len(terminated)
        logging.info("Instance needed:{} count:{} terminated:{} total:{} "
                 "limit:{}".format(
                    instance_needed, instance_count, len(terminated),
                    len(nodes), self.instance_limit))
        return self.is_resource_available(
            self.instance_limit, instance_count, instance_needed)

    def is_security_group_available(self, security_group_needed):
        security_group_count = len(self.client.ex_list_security_groups())
        logging.info("Security group needed:{} count:{} limit:{}".format(
            security_group_needed, security_group_count,
            self.security_group_limit))
        return self.is_resource_available(
            self.security_group_limit, security_group_count,
            security_group_needed)


def make_client(access_key, secret_key, region):
    aws_driver = libcloud.compute.providers.get_driver(
        libcloud.compute.types.Provider.EC2)
    return aws_driver(access_key, secret_key, region=region)
