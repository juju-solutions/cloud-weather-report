import abc

__metaclass__ = type


class CloudResource:
    __metaclass__ = abc.ABCMeta

    def __init__(self, instance_limit, security_group_limit):
        self.instance_limit = instance_limit
        self.security_group_limit = security_group_limit

    @abc.abstractmethod
    def is_instance_available(self, instance_needed):
        raise NotImplemented

    @abc.abstractmethod
    def is_security_group_available(self, security_group_needed):
        raise NotImplemented

    @staticmethod
    def is_resource_available(limit, count, needed):
        if limit - (count + needed) >= 0:
            return True
        return False
