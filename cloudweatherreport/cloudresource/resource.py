import logging
import os
import yaml

import cloudweatherreport.cloudresource.aws as aws
import cloudweatherreport.cloudresource.gce as gce
import cloudweatherreport.cloudresource.azure as azure
from cloudweatherreport.utils import juju_cmd


class UnknownCloudName(Exception):
    pass


class UnknownCredentialName(Exception):
    pass


class CloudNotSupported(Exception):
    pass


def get_credential_name(creds, cloud_name):
    cred_name = creds.get('credentials', {}).get(cloud_name, {}).get(
        'default-credential')
    if cred_name:
        return cred_name

    names = list(creds.get('credentials', {}).get(cloud_name, {}).keys())
    try:
        names.remove('default-region')
    except ValueError:
        pass
    if len(names) > 1:
        raise ValueError(
            'More than one credential is available. Set default juju '
            'credential or set JUJU_CREDENTIAL_NAME system variable.')
    return names[0]


def get_credentials(cloud, name=None):
    """Get cloud credentials from the juju credentials command."""
    cmd = 'list-credentials {} --format yaml --show-secrets'.format(cloud)
    creds = juju_cmd(cmd)
    creds = yaml.safe_load(creds)
    if not creds or not creds.get('credentials', {}).get(cloud):
        raise UnknownCloudName('Cloud not found: {}'.format(cloud))

    name = get_credential_name(creds, cloud) if not name else name
    try:
        credentials = creds['credentials'][cloud][name]
    except KeyError:
        raise UnknownCredentialName(
            'Credential name not found cloud:{} name:{}'.format(cloud, name))
    return credentials


def _aws_client(creds, region, instance_limit, security_group_limit):
    instance_limit = instance_limit or aws.INSTANCE_LIMIT
    security_group_limit = security_group_limit or aws.SECURITY_GROUP_LIMIT
    client = aws.AWS(
        access_key=creds['access-key'],
        secret_key=creds['secret-key'],
        region=region,
        instance_limit=instance_limit,
        security_group_limit=security_group_limit)
    return client


def _gce_client(creds, region, instance_limit, security_group_limit,
                cpu_limit):
    instance_limit = instance_limit or gce.INSTANCE_LIMIT
    security_group_limit = security_group_limit or gce.SECURITY_GROUP_LIMIT
    cpu_limit = cpu_limit or gce.CPU_LIMIT
    client = gce.GCE(
        sa_email=creds['client-email'],
        key=creds['private-key'],
        region=region,
        project_id=creds['project-id'],
        instance_limit=instance_limit,
        security_group_limit=security_group_limit,
        cpu_limit=cpu_limit
    )
    return client


def _azure_client(creds, region, instance_limit, security_group_limit,
                  cpu_limit, azure_tenant_id):
    instance_limit = instance_limit or azure.INSTANCE_LIMIT
    security_group_limit = security_group_limit or azure.SECURITY_GROUP_LIMIT
    cpu_limit = cpu_limit or azure.CORE_LIMIT
    client = azure.Azure(
        tenant_id=azure_tenant_id,
        subscription_id=creds['subscription-id'],
        application_id=creds['application-id'],
        application_password=creds['application-password'],
        region=region,
        instance_limit=instance_limit,
        security_group_limit=security_group_limit,
        core_limit=cpu_limit
    )
    return client


def is_resource_available(cloud, region,
                          num_of_instances,
                          num_of_security_groups,
                          num_of_cpus,
                          instance_limit=None,
                          security_group_limit=None,
                          cpu_limit=None,
                          credentials_name=None,
                          azure_tenant_id=None):
    """Determine if resources are available to perform tests.

    Check if instance/machine, security group and CPU resources
    are available before performing cwr tests.

    :param cloud: Cloud name
    :param region: Cloud region
    :param num_of_instances: Number of instances needed to perform tests.
    :param num_of_security_groups: Number of security groups needed.
    :param num_of_cpus: Number of CPUs needed
    :param instance_limit:  Instance or machine limit
    :param security_group_limit: Security group limit
    :param cpu_limit:  CPU or core limit. Ignored for AWS cloud.
    :param credentials_name:  Juju credentials name.
    :param azure_tenant_id: Azure tenant id if cloud is set to azure. If set to
      None, it tries to use the AZURE_TENANT_ID environment variable.
    :return boolean
    """
    logging.info('Checking resource for {}'.format(cloud))
    azure_tenant_id = azure_tenant_id or os.getenv('AZURE_TENANT_ID')
    creds = get_credentials(cloud, credentials_name)

    if 'aws' in cloud.lower():
        client = _aws_client(
            creds, region, instance_limit, security_group_limit)
        security_available = client.is_security_group_available(
            num_of_security_groups)
    elif 'google' in cloud.lower():
        client = _gce_client(
            creds, region, instance_limit, security_group_limit, cpu_limit)
        security_available = client.is_security_group_available(
            num_of_security_groups)
    elif 'azure' in cloud.lower():
        if azure_tenant_id is None:
            raise CloudNotSupported(
                'Tenant ID is required to check for Azure resources')
        client = _azure_client(
            creds, region, instance_limit, security_group_limit, cpu_limit,
            azure_tenant_id)
        # Azure does not support listing security groups
        security_available = True
    else:
        raise CloudNotSupported('Cloud not supported {}'.format(cloud))

    instance_available = client.is_instance_available(
        num_of_instances, num_of_cpus)

    return instance_available is True and security_available is True
