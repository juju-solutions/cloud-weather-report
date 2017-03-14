import abc
import logging

__metaclass__ = type


class CloudResource:
    __metaclass__ = abc.ABCMeta

    def __init__(self, instance_limit, security_group_limit, cpu_limit):
        self.instance_limit = instance_limit
        self.security_group_limit = security_group_limit
        self.cpu_limit = cpu_limit

    @abc.abstractmethod
    def is_instance_available(self, number_of_instances, number_of_cpus=None):
        """Return True if the num of requested instance and CPU are available.

        :param number_of_instances: Number of requested instance.
        :param number_of_cpus: Number of requested CPUs.
        :return: boolean
        """
        raise NotImplemented

    @abc.abstractmethod
    def is_security_group_available(self, number_of_security_groups):
        """Return True if the num of requested security groups are available.

        :param number_of_security_groups: Number of requested security groups.
        :return: boolean
        """
        raise NotImplemented

    @staticmethod
    def is_resource_available(request, count, limit):
        result = False
        if limit - (count + request) >= 0:
            result = True
        logging.info("Resource requested:{} count:{} limit:{} resource "
                     "available: {} ".format(request, count, limit, result))
        return result
