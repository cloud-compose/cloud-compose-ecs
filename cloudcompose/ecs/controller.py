import logging
from itertools import chain
from os import environ
from time import sleep

import boto3
import botocore
from cloudcompose.cluster.aws.cloudcontroller import CloudController
from cloudcompose.cluster.cloudinit import CloudInit
from cloudcompose.exceptions import CloudComposeException
from cloudcompose.util import require_env_var
from retrying import retry

from workflow import UpgradeWorkflow, Server

class Controller(object):
    def __init__(self, cloud_config):
        logging.basicConfig(level=logging.ERROR)
        self.logger = logging.getLogger(__name__)

        self.cloud_config = cloud_config
        self.config_data = cloud_config.config_data('cluster')
        self.aws = self.config_data['aws']
        self.name = self.config_data['name']

        self.ec2 = self._get_client('ec2')
        self.ecs = self._get_client('ecs')
        self.asg = self._get_client('autoscaling')
        self.elb = self._get_client('elb')
        self.alb = self._get_client('elbv2')

    @staticmethod
    def _get_client(client):
        return boto3.client(client, aws_access_key_id=require_env_var('AWS_ACCESS_KEY_ID'),
                            aws_secret_access_key=require_env_var('AWS_SECRET_ACCESS_KEY'),
                            region_name=environ.get('AWS_REGION', 'us-east-1'))

    def _cluster_create(self):
        """
        Create new ECS cluster with name
        :return: boolean representing success or failure
        """
        try:
            ecs_cluster = self._ecs_create_cluster(clusterName=self.name)
            return True if ecs_cluster['ResponseMetadata']['HTTPStatusCode'] == 200 else False
        except KeyError:
            return False

    def cluster_up(self, silent=False):
        """
        Update cluster configuration
        """
        if self._cluster_create():
            ci = CloudInit()
            cloud_controller = CloudController(self.cloud_config, silent=silent)
            cloud_controller.up(ci)
        else:
            print("ECS cluster {} does not exist and could not be created".format(self.name))

    def cluster_down(self, force):
        """
        Destroy an existing ECS cluster
        :param force: True if termination protection should be ignored
        """
        cloud_controller = CloudController(self.cloud_config)
        cloud_controller.down(force)

    def cleanup(self):
        """
        Remove launch configs and autoscaling group
        """
        cloud_controller = CloudController(self.cloud_config)
        cloud_controller.cleanup()

    def cluster_health(self):
        """
        ECS cluster must be active, EC2 instances must be active, and services must be active.
        :return: boolean representing health of entire ECS cluster
        """
        health_checks = [
            self._cluster_health(),
            self._instance_health(),
            self._service_health()
        ]
        return all(health_checks)

    def upgrade(self, single_step):
        """
        Replaces existing ECS container instances
        :param single_step: Whether to execute a single step (defaults to entire workflow)
        :return: None
        """
        servers = self._get_servers()
        workflow = UpgradeWorkflow(self, self.config_data['name'], servers)

        # Start upgrading container instances
        if single_step:
            print("Running single step")
            workflow.step()
        else:
            print("Starting upgrade of container instances:")
            while workflow.step():
                sleep(10)

    def instance_status(self, instance_id):
        filters = [{ 'Name': 'instance-id', 'Values': [instance_id] }]
        instances = self._ec2_describe_instances(Filters=filters)['Reservations']
        if len(instances) != 1:
            raise Exception('Expected one instance for %s and got %s' % (instance_id, len(instances)))
        return instances[0]['Instances'][0]['State']['Name']

    def _get_servers(self):
        """
        Describe instances for UpgradeWorkflow
        """
        instance_ids = [server['ec2InstanceId'] for server in self._get_ecs_instances()]
        filters = [{'Name': 'instance-state-name', 'Values': ['running']}]

        describe_instances = self._ec2_describe_instances(InstanceIds=instance_ids,
                                                          Filters=filters)
        servers = list(chain.from_iterable([
            reservation.get('Instances', []) for reservation in describe_instances.get('Reservations', [])
        ]))

        return [Server(private_ip=server['PrivateIpAddress'],
                instance_id=server['InstanceId'],
                instance_name=self.name) for server in servers]

    def _get_cluster(self):
        try:
            clusters = self._ecs_describe_clusters(clusters=[self.name, ])
            if not clusters['clusters']:
                raise CloudComposeException("{} cluster could not be found".format(self.name))
            return clusters['clusters']
        except KeyError:
            raise CloudComposeException("Could not retrieve cluster status for {}".format(self.name))

    def _get_ecs_services(self):
        cluster_services = self._ecs_list_services(cluster=self.name)

        if cluster_services.get('serviceArns', []):
            describe_services = self._ecs_describe_services(cluster=self.name,
                                                            services=cluster_services['serviceArns'])
            return describe_services['services']

        raise CloudComposeException("Services could not be retrieved for {}".format(self.name))

    def _get_ecs_instances(self):
        try:
            ecs_instances = self._ecs_list_container_instances(cluster=self.name)
            instances = self._ecs_describe_container_instances(cluster=self.name,
                                                               containerInstances=ecs_instances['containerInstanceArns'])
            return instances['containerInstances']
        except:
            raise CloudComposeException(
                'ECS container instances could not be retrieved for {}'.format(self.name))

    def _cluster_health(self):
        """
        The status of the cluster.
        :return: boolean representing status of the cluster
        """
        clusters = self._get_cluster()
        # ACTIVE indicates that you can register container instances with the cluster and instances can accept tasks.
        return all([cluster['status'] == 'ACTIVE' for cluster in clusters])

    def _service_health(self):
        """
        The status of services running on the cluster.
        :return: boolean representing status of all services
        """
        services = self._get_ecs_services()

        if services:
            load_balancers = list(chain.from_iterable([service.get('loadBalancers', []) for service in services]))
            load_balancers_healthy = self._check_load_balancers(load_balancers)

            return all([service['status'] == 'ACTIVE' for service in services]) and load_balancers_healthy
        else:
            # If there are no services running, there are no tasks to worry about.
            return True

    def _check_load_balancers(self, load_balancers):
        """
        The status of load balancers used by services on the cluster.
        :return: boolean representing status of all load balancers
        """
        albs = filter(None, [lb.get('targetGroupArn', None) for lb in load_balancers])
        elbs = filter(None, [lb.get('loadBalancerName', None) for lb in load_balancers])

        alb_statuses = list(chain.from_iterable([
            alb_status['TargetHealthDescriptions'] for alb_status in [
                self._alb_describe_target_health(TargetGroupArn=alb) for alb in albs
            ]
        ]))

        elb_statuses = list(chain.from_iterable([
            elb_status['InstanceStates'] for elb_status in [
                self._elb_describe_instance_health(LoadBalancerName=elb) for elb in elbs
            ]
        ]))

        alb_healthy = all([alb['TargetHealth']['State'] == 'healthy' for alb in alb_statuses])
        elb_healthy = all([elb['State'] == 'InService' for elb in elb_statuses])

        return alb_healthy and elb_healthy

    def _instance_health(self):
        """
        The status of the container instances.
        """
        instances = self._get_ecs_instances()
        asg = self._get_auto_scaling_group()
        if len(instances) != asg['DesiredCapacity']:
            return False
        else:
            return all([instance['status'] == 'ACTIVE' for instance in instances])

    def _get_auto_scaling_group(self):
        try:
            asgs = self._asg_describe_auto_scaling_groups(AutoScalingGroupNames=[self.name, ])
            if len(asgs['AutoScalingGroups']) == 1:
                return asgs['AutoScalingGroups'].pop()
            else:
                raise CloudComposeException('{} ASG is not unique'.format(self.name))
        except KeyError:
            raise CloudComposeException('AutoScalingGroup could not be retrieved for {}'.format(self.name))

    def replace_instance(self, instance_id):
        """
        Replace instance_id by telling Auto Scaling Group to terminate and replace the instance.
        :param instance_id: ECS container instance to terminate
        """
        self._asg_set_instance_health(InstanceId=instance_id, HealthStatus='Unhealthy')

    def _is_retryable_exception(exception):
        return not isinstance(exception, botocore.exceptions.ClientError)

    @retry(retry_on_exception=_is_retryable_exception, stop_max_delay=10000, wait_exponential_multiplier=500,
           wait_exponential_max=2000)
    def _ecs_create_cluster(self, **kwargs):
        return self.ecs.create_cluster(**kwargs)

    @retry(retry_on_exception=_is_retryable_exception, stop_max_delay=10000, wait_exponential_multiplier=500,
           wait_exponential_max=2000)
    def _ecs_describe_clusters(self, **kwargs):
        return self.ecs.describe_clusters(**kwargs)

    @retry(retry_on_exception=_is_retryable_exception, stop_max_delay=10000, wait_exponential_multiplier=500,
           wait_exponential_max=2000)
    def _ecs_list_services(self, **kwargs):
        return self.ecs.list_services(**kwargs)

    @retry(retry_on_exception=_is_retryable_exception, stop_max_delay=10000, wait_exponential_multiplier=500,
           wait_exponential_max=2000)
    def _ecs_describe_services(self, **kwargs):
        return self.ecs.describe_services(**kwargs)

    @retry(retry_on_exception=_is_retryable_exception, stop_max_delay=10000, wait_exponential_multiplier=500,
           wait_exponential_max=2000)
    def _ecs_list_container_instances(self, **kwargs):
        return self.ecs.list_container_instances(**kwargs)

    @retry(retry_on_exception=_is_retryable_exception, stop_max_delay=10000, wait_exponential_multiplier=500,
           wait_exponential_max=2000)
    def _ecs_describe_container_instances(self, **kwargs):
        return self.ecs.describe_container_instances(**kwargs)

    @retry(retry_on_exception=_is_retryable_exception, stop_max_delay=10000, wait_exponential_multiplier=500,
           wait_exponential_max=2000)
    def _asg_describe_auto_scaling_groups(self, **kwargs):
        return self.asg.describe_auto_scaling_groups(**kwargs)

    @retry(retry_on_exception=_is_retryable_exception, stop_max_delay=10000, wait_exponential_multiplier=500,
           wait_exponential_max=2000)
    def _asg_set_desired_capacity(self, **kwargs):
        return self.asg.set_desired_capacity(**kwargs)

    @retry(retry_on_exception=_is_retryable_exception, stop_max_delay=10000, wait_exponential_multiplier=500,
           wait_exponential_max=2000)
    def _asg_set_instance_health(self, **kwargs):
        return self.asg.set_instance_health(**kwargs)

    @retry(retry_on_exception=_is_retryable_exception, stop_max_delay=10000, wait_exponential_multiplier=500,
           wait_exponential_max=2000)
    def _alb_describe_target_health(self, **kwargs):
        return self.alb.describe_target_health(**kwargs)

    @retry(retry_on_exception=_is_retryable_exception, stop_max_delay=10000, wait_exponential_multiplier=500,
           wait_exponential_max=2000)
    def _elb_describe_instance_health(self, **kwargs):
        return self.elb.describe_instance_health(**kwargs)

    @retry(retry_on_exception=_is_retryable_exception, stop_max_delay=10000, wait_exponential_multiplier=500,
           wait_exponential_max=2000)
    def _ec2_describe_instances(self, **kwargs):
        return self.ec2.describe_instances(**kwargs)
