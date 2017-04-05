from textwrap import dedent
from unittest import TestCase
import os

from mock import patch
from yaml import safe_load

from cloudweatherreport.cloudresource.resource import (
    get_credentials,
    is_resource_available,
    CloudNotSupported,
    UnknownCloudName,
    UnknownCredentialName,
)


class TestGetCredentials(TestCase):

    fake_creds = dedent("""\
    credentials:
        aws:
            default-credential: cred
            cred:
                auth-type: access-key
                access-key: aws-access-key
                secret-key: aws-secret-key
            cred2:
                auth-type: access-key2
                access-key: aws-access-key2
                secret-key: aws-secret-key2
        google:
            default-credential: cred
            cred:
                auth-type: oauth
                client-email: thedude@example.com
                client-id: 1234
                project-id: p-id
                private-key: |
                  asdf1234
                """)
    fake_creds_no_default = dedent("""\
    credentials:
        aws:
            default-region: us-west-2
            cred4:
                auth-type: access-key4
                access-key: aws-access-key4
                secret-key: aws-secret-key4
            cred3:
                auth-type: access-key3
                access-key: aws-access-key3
                secret-key: aws-secret-key3
        azure:
            cred6:
              application-id: 1234-abc
              application-password: pass
              subscription-id: asdf-1234
        google:
            cred5:
                client-email: thedude@example.com5
                client-id: 12345
                project-id: p-id2
                private-key: |
                  asdf12345
                """)

    @patch('subprocess.check_output', autospec=True)
    def test_get_credentials_default_creds(self, cc_mock):
        cc_mock.return_value = self.fake_creds
        creds = get_credentials('aws')
        expected = safe_load(self.fake_creds)['credentials']['aws']['cred']
        self.assertEqual(creds, expected)

        creds = get_credentials('google')
        expected = safe_load(self.fake_creds)['credentials']['google']['cred']
        self.assertEqual(creds, expected)

    @patch('subprocess.check_output', autospec=True)
    def test_get_credentials_default_creds_named_cred(self, cc_mock):
        cc_mock.return_value = self.fake_creds
        creds = get_credentials('aws', 'cred')
        expected = safe_load(self.fake_creds)['credentials']['aws']['cred']
        self.assertEqual(creds, expected)

        creds = get_credentials('google', 'cred')
        expected = safe_load(self.fake_creds)['credentials']['google']['cred']
        self.assertEqual(creds, expected)

    @patch('subprocess.check_output', autospec=True)
    def test_get_credentials_more_than_one_credential(self, cc_mock):
        cc_mock.return_value = self.fake_creds_no_default
        with self.assertRaisesRegexp(ValueError, "More than one credential"):
            get_credentials('aws')

        creds = get_credentials('google')
        expected = safe_load(self.fake_creds_no_default)
        expected = expected['credentials']['google']['cred5']
        self.assertEqual(creds, expected)

    @patch('subprocess.check_output', autospec=True)
    def test_get_credentials_no_default_creds_named_cred(self, cc_mock):
        cc_mock.return_value = self.fake_creds_no_default
        creds = get_credentials('aws', 'cred4')
        expected = safe_load(self.fake_creds_no_default)
        expected = expected['credentials']['aws']['cred4']
        self.assertEqual(creds, expected)

        creds = get_credentials('google', 'cred5')
        expected = safe_load(self.fake_creds_no_default)
        expected = expected['credentials']['google']['cred5']
        self.assertEqual(creds, expected)

    @patch('subprocess.check_output', autospec=True)
    def test_get_credentials_unknown_cloud_name(self, cc_mock):
        cc_mock.return_value = 'credentials: {}'
        with self.assertRaisesRegexp(UnknownCloudName, "Cloud not found:"):
            get_credentials('foo')

    @patch('subprocess.check_output', autospec=True)
    def test_get_credentials_unknown_cred_name(self, cc_mock):
        cc_mock.return_value = self.fake_creds_no_default
        with self.assertRaisesRegexp(
                UnknownCredentialName, "Credential name not found"):
            get_credentials('google', 'foo')


class TestIsResourceAvailable(TestCase):

    @patch('subprocess.check_output', autospec=True)
    @patch('cloudweatherreport.cloudresource.aws.AWS', autospec=True)
    def test_is_resource_available_aws(self, aws_mock, cc_mock):
        aws_mock.return_value.is_security_group_available.return_value = True
        aws_mock.return_value.is_instance_available.return_value = True
        cc_mock.return_value = TestGetCredentials.fake_creds
        result = is_resource_available('aws', 'us-west-1', 1, 1, 1)
        self.assertIs(result, True)
        cc_mock.assert_called_once_with(
            ['juju', 'list-credentials', 'aws', '--format', 'yaml',
             '--show-secrets'])
        aws_mock.assert_called_once_with(
            access_key='aws-access-key', instance_limit=20,
            region='us-west-1', secret_key='aws-secret-key',
            security_group_limit=500)

    @patch('subprocess.check_output', autospec=True)
    @patch('cloudweatherreport.cloudresource.gce.GCE', autospec=True)
    def test_is_resource_availablegce(self, gce_mock, cc_mock):
        gce_mock.return_value.is_security_group_available.return_value = True
        gce_mock.return_value.is_instance_available.return_value = True
        cc_mock.return_value = TestGetCredentials.fake_creds_no_default
        result = is_resource_available('google', 'us-west1', 1, 1, 1)
        self.assertIs(result, True)
        cc_mock.assert_called_once_with(
            ['juju', 'list-credentials', 'google', '--format', 'yaml',
             '--show-secrets'])
        gce_mock.assert_called_once_with(
            cpu_limit=24, instance_limit=200, key='asdf12345\n',
            project_id='p-id2', region='us-west1',
            sa_email='thedude@example.com5', security_group_limit=100)

    @patch('subprocess.check_output', autospec=True)
    @patch('cloudweatherreport.cloudresource.azure.Azure', autospec=True)
    def test_is_resource_available_azure(self, azure_mock, cc_mock):
        azure_mock.return_value.is_instance_available.return_value = True
        cc_mock.return_value = TestGetCredentials.fake_creds_no_default
        os.environ['AZURE_TENANT_ID'] = 'tenant id'
        result = is_resource_available('azure', 'westus', 1, 1, 1)
        del os.environ['AZURE_TENANT_ID']
        self.assertIs(result, True)
        cc_mock.assert_called_once_with(
            ['juju', 'list-credentials', 'azure', '--format', 'yaml',
             '--show-secrets'])
        azure_mock.assert_called_once_with(
            application_id='1234-abc', application_password='pass',
            core_limit=20, instance_limit=60, region='westus',
            security_group_limit=100, subscription_id='asdf-1234',
            tenant_id='tenant id')

    @patch('subprocess.check_output', autospec=True)
    @patch('cloudweatherreport.cloudresource.azure.Azure', autospec=True)
    def test_is_resource_available_raises_exception(self, azure_mock, cc_mock):
        cc_mock.return_value = 'credentials: {}'
        with self.assertRaisesRegexp(UnknownCloudName, 'Cloud not found'):
            is_resource_available('azure', 'westus', 1, 1, 1)
        cc_mock.assert_called_once_with(
            ['juju', 'list-credentials', 'azure', '--format', 'yaml',
             '--show-secrets'])

        cc_mock.return_value = TestGetCredentials.fake_creds_no_default
        with self.assertRaisesRegexp(
                CloudNotSupported, 'Tenant ID is required'):
            is_resource_available('azure', 'westus', 1, 1, 1)
